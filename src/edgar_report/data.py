from __future__ import annotations

import csv
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Tuple

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
S1_F1_FORMS = {"S-1", "F-1"}


@dataclass
class DataConfig:
    project: str = "sec-edgar-ralph"
    dataset: str = "edgar"
    table: str = "fact_filing_enriched"
    report_year: int = 2026
    location: str = "US"


def get_bigquery_sql(config: DataConfig) -> str:
    table_ref = f"`{config.project}.{config.dataset}.{config.table}`"
    return f"""
WITH base AS (
  SELECT
    standardized_name,
    filingDate,
    formType,
    accessionNumber
  FROM {table_ref}
  WHERE EXTRACT(YEAR FROM filingDate) = {config.report_year}
    AND filingDate < DATE_TRUNC(CURRENT_DATE(), MONTH)
    AND formType IN ('S-1', 'F-1')
    AND standardized_name IS NOT NULL
    AND accessionNumber IS NOT NULL
)
SELECT
  standardized_name,
  EXTRACT(MONTH FROM filingDate) AS filing_month,
  COUNT(DISTINCT accessionNumber) AS filing_count
FROM base
GROUP BY 1, 2
ORDER BY standardized_name, filing_month
""".strip()


def _ensure_bq_cli() -> None:
    if shutil.which("bq") is None:
        raise RuntimeError(
            "BigQuery mode requires the `bq` CLI, but it was not found in PATH. "
            "Install Google Cloud SDK and run `gcloud auth application-default login` and "
            "`gcloud auth login`, then retry."
        )


def load_from_bigquery(config: DataConfig) -> List[Dict[str, str]]:
    _ensure_bq_cli()
    sql = get_bigquery_sql(config)
    cmd = [
        "bq",
        "query",
        "--use_legacy_sql=false",
        "--format=csv",
        f"--location={config.location}",
        f"--project_id={config.project}",
        sql,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        raise RuntimeError(
            "BigQuery query failed. Ensure your account can access the table and billing is enabled for the project. "
            f"Command: {' '.join(cmd[:-1])} <SQL>. Error: {stderr}"
        ) from exc

    rows: List[Dict[str, str]] = []
    reader = csv.DictReader(result.stdout.splitlines())
    for row in reader:
        rows.append(row)
    return rows


def load_from_csv(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    required = {"standardized_name", "filingDate", "formType", "accessionNumber"}
    missing = required.difference(rows[0].keys() if rows else set())
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
    return rows


def aggregate_s1_f1_monthly(raw_rows: List[Dict[str, str]], report_year: int = 2026) -> Tuple[List[str], List[List[str]]]:
    cutoff = date.today().replace(day=1)
    month_agent_accessions: Dict[Tuple[str, int], set] = defaultdict(set)

    pre_aggregated = all(k in raw_rows[0] for k in ["standardized_name", "filing_month", "filing_count"]) if raw_rows else False

    if pre_aggregated:
        month_agent_count: Dict[Tuple[str, int], int] = defaultdict(int)
        for row in raw_rows:
            agent = (row.get("standardized_name") or "").strip()
            if not agent:
                continue
            month = int(row.get("filing_month", "0"))
            count = int(row.get("filing_count", "0"))
            month_agent_count[(agent, month)] += count
    else:
        for row in raw_rows:
            form_type = (row.get("formType") or "").strip()
            if form_type not in S1_F1_FORMS:
                continue
            agent = (row.get("standardized_name") or "").strip()
            accession = (row.get("accessionNumber") or "").strip()
            date_str = (row.get("filingDate") or "").strip()
            if not agent or not accession or not date_str:
                continue
            try:
                filing_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if filing_date.year != report_year or filing_date >= cutoff:
                continue
            month_agent_accessions[(agent, filing_date.month)].add(accession)

        month_agent_count = {k: len(v) for k, v in month_agent_accessions.items()}

    agents = sorted({agent for agent, _ in month_agent_count.keys()})
    headers = ["Filing Agent", *MONTH_LABELS, "Total"]
    rows: List[List[str]] = []

    col_totals = [0] * 12
    grand_total = 0
    for agent in agents:
        month_counts = [month_agent_count.get((agent, m), 0) for m in range(1, 13)]
        row_total = sum(month_counts)
        col_totals = [col_totals[i] + month_counts[i] for i in range(12)]
        grand_total += row_total
        rows.append([agent, *[str(v) for v in month_counts], str(row_total)])

    rows.append(["Total", *[str(v) for v in col_totals], str(grand_total)])
    return headers, rows
