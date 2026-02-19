from __future__ import annotations

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
        out.extend(f"xref\n0 {len(self.objects)+1}\n".encode())
        out.extend(b"0000000000 65535 f \n")
        for pos in xref[1:]:
            out.extend(f"{pos:010d} 00000 n \n".encode())
        out.extend(
            (
                "trailer\n"
                f"<< /Size {len(self.objects)+1} /Root {root_obj} 0 R >>\n"
                "startxref\n"
                f"{xref_pos}\n"
                "%%EOF\n"
            ).encode()
        )
        return bytes(out)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(output_path: str, headers: list[str], rows: list[list[str]], analysis_text: str) -> None:
    width, height = 792, 612
    lines: list[str] = []

    def text(x: int, y: int, size: int, content: str):
        lines.append("BT")
        lines.append(f"/F1 {size} Tf")
        lines.append(f"{x} {y} Td")
        lines.append(f"({_esc(content)}) Tj")
        lines.append("ET")

    text(30, 580, 18, "EDGAR Agents S-1/F-1 Monthly Filing Report (2026)")
    text(30, 560, 11, "12-month landscape table includes Jan-Dec, with row and column totals.")

    y = 535
    col_widths = [150] + [42] * 12 + [50]
    x_positions = [30]
    for w in col_widths[:-1]:
        x_positions.append(x_positions[-1] + w)

    for i, h in enumerate(headers):
        text(x_positions[i] + 2, y, 8, h)
    y -= 14

    for row in rows:
        for i, cell in enumerate(row):
            text(x_positions[i] + 2, y, 7, str(cell))
        y -= 12
        if y < 280:
            break

    text(30, 250, 12, "Executive Analysis")
    y = 234
    for para in analysis_text.split("\n"):
        for wrapped in textwrap.wrap(para, width=130) or [""]:
            text(30, y, 9, wrapped)
            y -= 11
            if y < 25:
                break
        if y < 25:
            break

    content_stream = "\n".join(lines).encode("latin-1", errors="replace")

    pdf = SimplePdf()
    font_obj = pdf.add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content_obj = pdf.add_object(f"<< /Length {len(content_stream)} >>\nstream\n".encode() + content_stream + b"\nendstream")
    page_obj = pdf.add_object(
        (
            f"<< /Type /Page /Parent 4 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode()
    )
    pages_obj = pdf.add_object(f"<< /Type /Pages /Kids [{page_obj} 0 R] /Count 1 >>".encode())
    catalog_obj = pdf.add_object(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode())

    with open(output_path, "wb") as f:
        f.write(pdf.build(catalog_obj))
