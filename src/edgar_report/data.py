from __future__ import annotations

import csv
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Dict, List, Tuple

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SEC_16_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}

MF_FORMS = {
    item.strip().upper()
    for item in (
        "487,497,24F-2NT,24F-2NT/A,40-17F1,40-17F1/A,40-17F2,40-17F2/A,40-17G,40-17G/A,40-17GCS,40-24B2,"
        "40-24B2/A,40-33,40-33/A,40-6B,40-6B/A,40-8B25,40-8F-2,40-8F-2/A,40-APP,40-APP/A,40-F,40-F/A,"
        "40FR12B,40FR12B/A,40FR12G,40FR12G/A,40-OIP,40-OIP/A,485APOS,485BPOS,485BXT,486APOS,486BPOS,"
        "486BXT,497AD,497H2,497J,497K,N-14,N-14 8C,N-14 8C/A,N-14/A,N-14MEF,N-18F1,N-18F1/A,N-1A,N-1A/A,"
        "N-2,N-2/A,N-23C-2,N-23C-2/A,N-23C3A,N-23C3A/A,N-23C3B,N-23C3C,N-23C3C/A,N-2ASR,N-2MEF,N-30B-2,"
        "N-30D,N-30D/A,N-4,N-4/A,N-54A,N-54A/A,N-54C,N-6,N-6/A,N-6F,N-6F/A,N-8A,N-8A/A,N-8B-2,N-8B-2/A,"
        "N-8B-4,N-8F,N-8F/A,N-CEN,N-CEN/A,N-CR,N-CR/A,N-CSR,N-CSR/A,N-CSRS,N-CSRS/A,N-MFP,N-MFP/A,"
        "N-MFP1,N-MFP1/A,N-MFP2,N-MFP2/A,NPORT-EX,NPORT-EX/A,NPORT-P,NPORT-P/A,N-PX,N-PX/A,N-Q,N-Q/A,"
        "NRSRO-CE,NRSRO-CE/A,NRSRO-UPD,NSAR-A,NSAR-A/A,NSAR-AT,NSAR-B,NSAR-B/A,NSAR-BT,NSAR-U,NSAR-U/A,"
        "POS 8C,POS AMI,N-MFP3,N-MFP3/A"
    ).split(",")
    if item.strip()
}


@dataclass(frozen=True)
class FilingBucket:
    name: str
    slug: str
    matcher: Callable[[Dict[str, str]], bool]


def _normalized_form(row: Dict[str, str]) -> str:
    return (row.get("formType") or "").strip().upper()


def _match_exact_forms(allowed_forms: set[str]) -> Callable[[Dict[str, str]], bool]:
    normalized = {f.upper() for f in allowed_forms}
    return lambda row: _normalized_form(row) in normalized


def _match_all(_: Dict[str, str]) -> bool:
    return True


def _match_all_but_sec16(row: Dict[str, str]) -> bool:
    return _normalized_form(row) not in SEC_16_FORMS


def _match_spac_s1(row: Dict[str, str]) -> bool:
    return _normalized_form(row) == "S-1" and (row.get("company_sicDescription") or "").strip().upper() == "BLANK CHECKS"


def get_filing_buckets() -> list[FilingBucket]:
    return [
        FilingBucket(name="S-1/F-1", slug="s1_f1", matcher=_match_exact_forms({"S-1", "F-1"})),
        FilingBucket(name="10-K/10-Q", slug="10k_10q", matcher=_match_exact_forms({"10-K", "10-Q"})),
        FilingBucket(name="All", slug="all", matcher=_match_all),
        FilingBucket(name="All but Sec 16", slug="all_but_sec16", matcher=_match_all_but_sec16),
        FilingBucket(name="20-Fs", slug="20f", matcher=_match_exact_forms({"20-F"})),
        FilingBucket(name="S-4 & F-4", slug="s4_f4", matcher=_match_exact_forms({"S-4", "F-4"})),
        FilingBucket(name="SPAC S-1s", slug="spac_s1", matcher=_match_spac_s1),
        FilingBucket(name="DEF14As", slug="def14a", matcher=_match_exact_forms({"DEF14A"})),
        FilingBucket(name="MF", slug="mf", matcher=_match_exact_forms(MF_FORMS)),
        FilingBucket(name="485BPOS", slug="485bpos", matcher=_match_exact_forms({"485BPOS"})),
        FilingBucket(name="N-2", slug="n2", matcher=_match_exact_forms({"N-2"})),
        FilingBucket(name="N-CSR", slug="n_csr", matcher=_match_exact_forms({"N-CSR"})),
        FilingBucket(name="N-PORT", slug="n_port", matcher=_match_exact_forms({"N-PORT"})),
        FilingBucket(name="N-CEN", slug="n_cen", matcher=_match_exact_forms({"N-CEN"})),
    ]


def get_agent_name(row: Dict[str, str]) -> str:
    return (row.get("standardized_name") or "").strip()


@dataclass
class DataConfig:
    project: str = "sec-edgar-ralph"
    dataset: str = "edgar"
    table: str = "fact_filing_enriched"
    report_year: int = 2026
    location: str = "US"


def _parse_date(raw_date: str) -> date | None:
    try:
        return datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def get_completed_month_count(
    raw_rows: List[Dict[str, str]], report_year: int, force_full_year: bool = False
) -> int:
    if force_full_year:
        return 12

    today = date.today()
    if report_year < today.year:
        return 12
    if report_year == today.year:
        return max(today.month - 1, 0)

    months_with_data = set()
    for row in raw_rows:
        filing_date = _parse_date((row.get("filingDate") or "").strip())
        if not filing_date or filing_date.year != report_year:
            continue
        months_with_data.add(filing_date.month)

    return max(months_with_data) if months_with_data else 0


def _resolve_report_cutoff(
    raw_rows: List[Dict[str, str]], report_year: int, force_full_year: bool = False
) -> date:
    completed_month_count = get_completed_month_count(raw_rows, report_year, force_full_year=force_full_year)
    if completed_month_count <= 0:
        return date(report_year, 1, 1)
    if completed_month_count >= 12:
        return date(report_year + 1, 1, 1)
    return date(report_year, completed_month_count + 1, 1)


def get_bigquery_sql(config: DataConfig) -> str:
    table_ref = f"`{config.project}.{config.dataset}.{config.table}`"
    return f"""
SELECT
  standardized_name,
  filingDate,
  formType,
  accessionNumber,
  company_sicDescription
FROM {table_ref}
WHERE EXTRACT(YEAR FROM filingDate) = {config.report_year}
  AND standardized_name IS NOT NULL
  AND accessionNumber IS NOT NULL
ORDER BY filingDate, standardized_name, accessionNumber
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
        "--max_rows=1000000",
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
    keys = set(rows[0].keys()) if rows else set()
    required = {"filingDate", "formType", "accessionNumber"}
    missing = required.difference(keys)
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
    if "standardized_name" not in keys:
        raise ValueError("CSV must include `standardized_name`")
    return rows


def aggregate_monthly_by_bucket(
    raw_rows: List[Dict[str, str]],
    bucket: FilingBucket,
    report_year: int = 2026,
    force_full_year: bool = False,
) -> Tuple[List[str], List[List[str]]]:
    cutoff = _resolve_report_cutoff(raw_rows, report_year, force_full_year=force_full_year)
    month_agent_accessions: Dict[Tuple[str, int], set] = defaultdict(set)

    for row in raw_rows:
        if not bucket.matcher(row):
            continue
        agent = get_agent_name(row)
        accession = (row.get("accessionNumber") or "").strip()
        filing_date = _parse_date((row.get("filingDate") or "").strip())
        if not agent or not accession or not filing_date:
            continue
        if filing_date.year != report_year or filing_date >= cutoff:
            continue
        month_agent_accessions[(agent, filing_date.month)].add(accession)

    month_agent_count = {k: len(v) for k, v in month_agent_accessions.items()}

    agents = sorted(
        {agent for agent, _ in month_agent_count.keys()},
        key=lambda agent: (-sum(month_agent_count.get((agent, m), 0) for m in range(1, 13)), agent),
    )
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
