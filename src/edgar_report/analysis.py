from __future__ import annotations

import json
import os
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


def _fallback_analysis(rows: list[list[str]], headers: list[str]) -> str:
    if len(rows) <= 1:
        return "No completed-month S-1/F-1 filings were found for 2026 in the provided dataset."
    agent_rows = [r for r in rows if r[0] != "Total"]
    total_row = next((r for r in rows if r[0] == "Total"), None)
    top = max(agent_rows, key=lambda r: int(r[-1])) if agent_rows else None
    if not top or not total_row:
        return "No completed-month S-1/F-1 filings were found for 2026 in the provided dataset."
    monthly_values = [int(x) for x in total_row[1:-1]]
    best_idx = monthly_values.index(max(monthly_values))
    best_month = headers[1 + best_idx]
    return dedent(
        f"""
        ## Executive Snapshot
        - Top filing agent (S-1/F-1): {top[0]} with {top[-1]} filings YTD.
        - Peak month so far: {best_month} with {monthly_values[best_idx]} total filings.

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


def generate_executive_analysis(headers: list[str], rows: list[list[str]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_analysis(rows, headers)

    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Analyze this S-1/F-1 filing table for 2026 completed months only. "
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
        return _fallback_analysis(rows, headers)
