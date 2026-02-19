from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime
from textwrap import dedent
from urllib import request

SYSTEM_PROMPT = (
    "You are the Chief Strategy Officer at EDGAR Agents. Provide executive-level strategic "
    "analysis focused on filing-agent competition, form-type trends, market share opportunities, "
    "and growth recommendations. Avoid legal advice."
)


def _rows_to_markdown(headers: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([line, sep, *body])


def _build_prior_year_context(raw_rows: list[dict[str, str]], report_year: int) -> str:
    prior_year = report_year - 1
    cutoff = date.today().replace(day=1)
    cutoff_month = cutoff.month

    counts_by_month: dict[int, set[str]] = defaultdict(set)
    for row in raw_rows:
        if (row.get("formType") or "").strip() not in {"S-1", "F-1"}:
            continue

        accession = (row.get("accessionNumber") or "").strip()
        filing_date_str = (row.get("filingDate") or "").strip()
        if not accession or not filing_date_str:
            continue

        try:
            filing_date = datetime.strptime(filing_date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue

        if filing_date.year != prior_year:
            continue

        if cutoff_month > 1 and filing_date.month > cutoff_month - 1:
            continue

        counts_by_month[filing_date.month].add(accession)

    month_pairs = [f"{month}:{len(counts_by_month.get(month, set()))}" for month in range(1, 13)]
    comparable_total = sum(len(counts_by_month.get(month, set())) for month in range(1, 13))

    return (
        f"Prior-year trend context for {prior_year} (S-1/F-1, comparable months only through "
        f"month {max(cutoff_month - 1, 0)}): total={comparable_total}; monthly={', '.join(month_pairs)}"
    )


def _fallback_analysis(rows: list[list[str]], headers: list[str], trend_context: str, report_year: int) -> str:
    if len(rows) <= 1:
        return f"No completed-month S-1/F-1 filings were found for {report_year} in the provided dataset."
    agent_rows = [r for r in rows if r[0] != "Total"]
    total_row = next((r for r in rows if r[0] == "Total"), None)
    top = max(agent_rows, key=lambda r: int(r[-1])) if agent_rows else None
    if not top or not total_row:
        return f"No completed-month S-1/F-1 filings were found for {report_year} in the provided dataset."
    monthly_values = [int(x) for x in total_row[1:-1]]
    completed_month_count = date.today().month - 1
    observed_values = monthly_values[: max(completed_month_count, 0)]
    if observed_values:
        best_idx = observed_values.index(max(observed_values))
        best_month = headers[1 + best_idx]
        best_month_value = observed_values[best_idx]
    else:
        best_month = "N/A"
        best_month_value = 0

    return dedent(
        f"""
        ## Executive Snapshot
        - Scope control: analysis is limited to completed months in {report_year}; months later in the year are displayed for layout only.
        - Top filing agent (S-1/F-1): {top[0]} with {top[-1]} filings YTD.
        - Peak completed month so far: {best_month} with {best_month_value} total filings.

        ## Prior-Year Continuity Context
        - {trend_context}

        ## Opportunity Map
        - Prioritize conversions in accounts currently served by top-volume competitors.
        - Build campaign timing around historically active months for registration filings.
        - Package premium S-1/F-1 support to improve win rates for high-value issuer mandates.

        ## Recommended Action Plan
        - Next 30 days: segment target accounts by agent share and recent activity.
        - Next 60 days: launch competitive takeout offers and SLA-backed service bundles.
        - Next 90 days: measure conversion rate, share gain, and filing throughput KPI trends.
        """
    ).strip()


def generate_executive_analysis(
    headers: list[str],
    rows: list[list[str]],
    raw_rows: list[dict[str, str]],
    report_year: int,
) -> str:
    trend_context = _build_prior_year_context(raw_rows, report_year)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_analysis(rows, headers, trend_context, report_year)

    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Analyze this S-1/F-1 filing table for {report_year}. "
                    f"The table displays all 12 months, but you must only analyze completed months through the current month cutoff. "
                    f"Do not comment on future months that have not happened yet. "
                    f"Use this prior-year continuity context for trend comparison: {trend_context}\n\n"
                    "Provide Market Insight Summary, Competitor trends, 90-day action plan, and long-term growth blueprint.\n\n"
                    + _rows_to_markdown(headers, rows)
                ),
            },
        ],
        "temperature": 0.2,
    }

    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]
    except Exception:
        return _fallback_analysis(rows, headers, trend_context, report_year)
