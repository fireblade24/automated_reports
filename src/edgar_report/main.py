from __future__ import annotations

import argparse
from pathlib import Path

from edgar_report.analysis import generate_executive_analysis
from edgar_report.data import DataConfig, aggregate_s1_f1_monthly, load_from_bigquery, load_from_csv
from edgar_report.pdf import build_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate EDGAR S-1/F-1 monthly report PDF")
    parser.add_argument("--output", default="output/edgar_s1_f1_report_2026.pdf")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--project", default="sec-edgar-ralph")
    parser.add_argument("--dataset", default="edgar")
    parser.add_argument("--table", default="fact_filing_enriched")
    parser.add_argument("--location", default="US")
    parser.add_argument("--from-csv", help="Optional local CSV input for offline proof-of-concept")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = DataConfig(
        project=args.project,
        dataset=args.dataset,
        table=args.table,
        report_year=args.year,
        location=args.location,
    )
    config = DataConfig(report_year=args.year)

    if args.from_csv:
        raw = load_from_csv(args.from_csv)
    else:
        raw = load_from_bigquery(config)

    headers, rows = aggregate_s1_f1_monthly(raw, report_year=args.year)
    analysis = generate_executive_analysis(headers, rows)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(str(output_path), headers, rows, analysis)

    print(f"Report created: {output_path}")


if __name__ == "__main__":
    main()
