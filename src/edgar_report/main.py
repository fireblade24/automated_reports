from __future__ import annotations

import argparse
from pathlib import Path

from edgar_report.analysis import generate_executive_analysis
from edgar_report.data import (
    DataConfig,
    aggregate_10k_10q_monthly,
    aggregate_s1_f1_monthly,
    load_from_bigquery,
    load_from_csv,
)
from edgar_report.pdf import build_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate EDGAR monthly report PDFs for filing buckets")
    parser.add_argument("--output", default="output")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--project", default="sec-edgar-ralph")
    parser.add_argument("--dataset", default="edgar")
    parser.add_argument("--table", default="fact_filing_enriched")
    parser.add_argument("--location", default="US")
    parser.add_argument("--from-csv", help="Optional local CSV input for offline proof-of-concept")
    parser.add_argument(
        "--pdf-engine",
        choices=["auto", "simple", "weasyprint"],
        default="auto",
        help="PDF renderer to use: auto (prefer WeasyPrint), simple (built-in fallback), or weasyprint only",
    )
    return parser.parse_args()


def _resolve_output_paths(output_arg: str, year: int) -> tuple[Path, Path]:
    output_path = Path(output_arg)
    if output_path.suffix.lower() == ".pdf":
        base = output_path.with_suffix("")
        s1f1_path = base.with_name(f"{base.name}_s1_f1_{year}.pdf")
        tenk_path = base.with_name(f"{base.name}_10k_10q_{year}.pdf")
        return s1f1_path, tenk_path

    output_path.mkdir(parents=True, exist_ok=True)
    return (
        output_path / f"edgar_s1_f1_report_{year}.pdf",
        output_path / f"edgar_10k_10q_report_{year}.pdf",
    )


def main() -> None:
    args = parse_args()
    config = DataConfig(
        project=args.project,
        dataset=args.dataset,
        table=args.table,
        report_year=args.year,
        location=args.location,
    )

    if args.from_csv:
        raw = load_from_csv(args.from_csv)
    else:
        raw = load_from_bigquery(config)

    s1_headers, s1_rows = aggregate_s1_f1_monthly(raw, report_year=args.year)
    s1_analysis = generate_executive_analysis(
        s1_headers,
        s1_rows,
        raw_rows=raw,
        report_year=args.year,
        bucket_label="S-1/F-1",
    )

    ten_headers, ten_rows = aggregate_10k_10q_monthly(raw, report_year=args.year)
    ten_analysis = generate_executive_analysis(
        ten_headers,
        ten_rows,
        raw_rows=raw,
        report_year=args.year,
        bucket_label="10-K/10-Q",
    )

    s1_output_path, ten_output_path = _resolve_output_paths(args.output, args.year)
    s1_output_path.parent.mkdir(parents=True, exist_ok=True)
    ten_output_path.parent.mkdir(parents=True, exist_ok=True)

    s1_engine = build_pdf(
        str(s1_output_path),
        s1_headers,
        s1_rows,
        s1_analysis,
        report_year=args.year,
        report_label="S-1/F-1",
        engine=args.pdf_engine,
    )
    ten_engine = build_pdf(
        str(ten_output_path),
        ten_headers,
        ten_rows,
        ten_analysis,
        report_year=args.year,
        report_label="10-K/10-Q",
        engine=args.pdf_engine,
    )

    print(f"Report created: {s1_output_path} (engine: {s1_engine})")
    print(f"Report created: {ten_output_path} (engine: {ten_engine})")


if __name__ == "__main__":
    main()
