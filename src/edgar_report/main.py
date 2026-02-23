from __future__ import annotations

import argparse
from pathlib import Path

from edgar_report.analysis import generate_executive_analysis
from edgar_report.data import DataConfig, aggregate_monthly_by_bucket, get_filing_buckets, load_from_bigquery, load_from_csv
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


def _resolve_output_path(output_arg: str, year: int, slug: str) -> Path:
    output_path = Path(output_arg)
    if output_path.suffix.lower() == ".pdf":
        base = output_path.with_suffix("")
        return base.with_name(f"{base.name}_{slug}_{year}.pdf")

    output_path.mkdir(parents=True, exist_ok=True)
    return output_path / f"edgar_{slug}_report_{year}.pdf"


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

    for bucket in get_filing_buckets():
        headers, rows = aggregate_monthly_by_bucket(raw, bucket=bucket, report_year=args.year)
        analysis = generate_executive_analysis(
            headers,
            rows,
            raw_rows=raw,
            report_year=args.year,
            bucket_label=bucket.name,
        )

        output_path = _resolve_output_path(args.output, args.year, bucket.slug)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        selected_engine = build_pdf(
            str(output_path),
            headers,
            rows,
            analysis,
            report_year=args.year,
            report_label=bucket.name,
            engine=args.pdf_engine,
        )

        print(f"Report created: {output_path} (engine: {selected_engine})")


if __name__ == "__main__":
    main()
