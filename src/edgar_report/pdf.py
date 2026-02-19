from __future__ import annotations

import html
import textwrap


class SimplePdf:
    def __init__(self) -> None:
        self.objects: list[bytes] = []

    def add_object(self, data: bytes) -> int:
        self.objects.append(data)
        return len(self.objects)

    def build(self, root_obj: int) -> bytes:
        out = bytearray(b"%PDF-1.4\n")
        xref = [0]
        for i, obj in enumerate(self.objects, start=1):
            xref.append(len(out))
            out.extend(f"{i} 0 obj\n".encode())
            out.extend(obj)
            out.extend(b"\nendobj\n")
        xref_pos = len(out)
        out.extend(f"xref\n0 {len(self.objects) + 1}\n".encode())
        out.extend(b"0000000000 65535 f \n")
        for pos in xref[1:]:
            out.extend(f"{pos:010d} 00000 n \n".encode())
        out.extend(
            (
                "trailer\n"
                f"<< /Size {len(self.objects) + 1} /Root {root_obj} 0 R >>\n"
                "startxref\n"
                f"{xref_pos}\n"
                "%%EOF\n"
            ).encode()
        )
        return bytes(out)


class PageCanvas:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def text(self, x: int, y: int, size: int, content: str) -> None:
        self.lines.append("BT")
        self.lines.append(f"/F1 {size} Tf")
        self.lines.append(f"{x} {y} Td")
        self.lines.append(f"({_esc(content)}) Tj")
        self.lines.append("ET")

    def build_stream(self) -> bytes:
        return "\n".join(self.lines).encode("latin-1", errors="replace")


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _new_page(pages: list[PageCanvas]) -> PageCanvas:
    page = PageCanvas()
    pages.append(page)
    return page


def _build_simple_pdf(output_path: str, headers: list[str], rows: list[list[str]], analysis_text: str) -> None:
    width, height = 792, 612
    pages: list[PageCanvas] = []

    page = _new_page(pages)
    page.text(30, 580, 18, "EDGAR Agents S-1/F-1 Monthly Filing Report (2026)")
    page.text(30, 560, 11, "12-month landscape table includes Jan-Dec, with row and column totals.")

    col_widths = [150] + [42] * 12 + [50]
    x_positions = [30]
    for w in col_widths[:-1]:
        x_positions.append(x_positions[-1] + w)

    def draw_table_header(canvas: PageCanvas, y_val: int) -> int:
        for i, cell in enumerate(headers):
            canvas.text(x_positions[i] + 2, y_val, 8, cell)
        return y_val - 14

    y = draw_table_header(page, 535)
    table_bottom_limit = 40
    for row in rows:
        if y < table_bottom_limit:
            page = _new_page(pages)
            page.text(30, 580, 13, "S-1/F-1 Filing Volume by Agent")
            y = draw_table_header(page, 560)
        for i, cell in enumerate(row):
            page.text(x_positions[i] + 2, y, 7, str(cell))
        y -= 12

    page = _new_page(pages)
    page.text(30, 580, 14, "Executive Analysis")
    y = 560
    for para in analysis_text.split("\n"):
        wrapped_lines = textwrap.wrap(para, width=130) or [""]
        for wrapped in wrapped_lines:
            if y < 30:
                page = _new_page(pages)
                page.text(30, 580, 14, "Executive Analysis (continued)")
                y = 560
            page.text(30, y, 9, wrapped)
            y -= 11

    page_streams = [p.build_stream() for p in pages]

    pdf = SimplePdf()
    font_obj = pdf.add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    content_obj_ids: list[int] = []
    for stream in page_streams:
        content_obj_ids.append(
            pdf.add_object(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        )

    page_obj_start = len(pdf.objects) + 1
    pages_obj_id = page_obj_start + len(page_streams)

    page_obj_ids: list[int] = []
    for content_obj_id in content_obj_ids:
        page_obj_ids.append(
            pdf.add_object(
                (
                    f"<< /Type /Page /Parent {pages_obj_id} 0 R /MediaBox [0 0 {width} {height}] "
                    f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_obj_id} 0 R >>"
                ).encode()
            )
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_obj_ids)
    pages_obj = pdf.add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_ids)} >>".encode())
    catalog_obj = pdf.add_object(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode())

    with open(output_path, "wb") as file_obj:
        file_obj.write(pdf.build(catalog_obj))


def _build_weasy_html(headers: list[str], rows: list[list[str]], analysis_text: str) -> str:
    head_cells = "".join(f"<th>{html.escape(cell)}</th>" for cell in headers)
    body_rows: list[str] = []
    for row in rows:
        css_class = "total-row" if row and row[0] == "Total" else ""
        body_rows.append(
            f"<tr class='{css_class}'>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>"
        )

    analysis_html = "".join(
        f"<p>{html.escape(line)}</p>" if line.strip() else "<p class='spacer'></p>"
        for line in analysis_text.splitlines()
    )

    return f"""
<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <style>
    @page {{
      size: Letter landscape;
      margin: 0.4in;
    }}
    body {{
      font-family: Arial, Helvetica, sans-serif;
      color: #1f2937;
      font-size: 10px;
    }}
    h1 {{
      margin: 0 0 2px 0;
      font-size: 20px;
      color: #0f3d69;
    }}
    .subtitle {{
      margin: 0 0 12px 0;
      color: #4b5563;
      font-size: 11px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      margin-bottom: 14px;
      font-size: 9px;
    }}
    th, td {{
      border: 1px solid #cbd5e1;
      padding: 4px;
      text-align: right;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    th:first-child, td:first-child {{
      text-align: left;
      width: 160px;
    }}
    th {{
      background: #e2e8f0;
      color: #0f172a;
      font-weight: 700;
    }}
    tr:nth-child(even) td {{
      background: #f8fafc;
    }}
    tr.total-row td {{
      font-weight: 700;
      background: #e5f0ff !important;
    }}
    h2 {{
      font-size: 14px;
      color: #0f3d69;
      margin: 12px 0 6px 0;
      page-break-after: avoid;
    }}
    p {{
      margin: 0 0 6px 0;
      line-height: 1.35;
      white-space: pre-wrap;
    }}
    .spacer {{
      margin: 0 0 8px 0;
    }}
  </style>
</head>
<body>
  <h1>EDGAR Agents S-1/F-1 Monthly Filing Report (2026)</h1>
  <p class='subtitle'>12-month landscape table includes Jan-Dec, with row and column totals.</p>

  <table>
    <thead><tr>{head_cells}</tr></thead>
    <tbody>
      {''.join(body_rows)}
    </tbody>
  </table>

  <h2>Executive Analysis</h2>
  {analysis_html}
</body>
</html>
""".strip()


def _build_weasy_pdf(output_path: str, headers: list[str], rows: list[list[str]], analysis_text: str) -> None:
    from weasyprint import HTML

    html_doc = _build_weasy_html(headers, rows, analysis_text)
    HTML(string=html_doc).write_pdf(output_path)


def build_pdf(
    output_path: str,
    headers: list[str],
    rows: list[list[str]],
    analysis_text: str,
    engine: str = "auto",
) -> str:
    if engine not in {"auto", "simple", "weasyprint"}:
        raise ValueError("engine must be one of: auto, simple, weasyprint")

    if engine in {"auto", "weasyprint"}:
        try:
            _build_weasy_pdf(output_path, headers, rows, analysis_text)
            return "weasyprint"
        except Exception:
            if engine == "weasyprint":
                raise

    _build_simple_pdf(output_path, headers, rows, analysis_text)
    return "simple"
