#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:-sec-edgar-ralph}"
DATASET="${2:-edgar}"
TABLE="${3:-fact_filing_enriched}"
LOCATION="${4:-US}"

command -v bq >/dev/null 2>&1 || { echo "bq CLI not found in PATH"; exit 1; }

echo "Checking access to ${PROJECT}.${DATASET}.${TABLE} in ${LOCATION}..."
bq --project_id="${PROJECT}" --location="${LOCATION}" query --use_legacy_sql=false \
  "SELECT COUNT(*) AS cnt FROM \
  \\`${PROJECT}.${DATASET}.${TABLE}\\`"

echo "BigQuery connectivity check passed."
