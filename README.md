# automated_reports

Automates a monthly EDGAR report for **S-1/F-1 combined filings** by filing agent, including:

- 2026 completed months only
- 12-month landscape table (Jan-Dec shown even when empty)
- row and column totals
- executive analysis section
- single stylized PDF output

## Data source

BigQuery table:
`sec-edgar-ralph.edgar.fact_filing_enriched`

Fields used for this POC:

- `standardized_name` (filing agent)
- `filingDate` (month)
- `formType` (S-1/F-1 bucket)
- `accessionNumber` (distinct filing count)

## Connect to BigQuery and pull real data

1. Install Google Cloud SDK (`gcloud` + `bq`):

```bash
gcloud --version
bq version
```

2. Authenticate:

```bash
gcloud auth login
gcloud auth application-default login
```

3. Set your default project (optional if using `--project`):

```bash
gcloud config set project sec-edgar-ralph
```

4. Verify table access:

```bash
bq --location=US query --use_legacy_sql=false 'SELECT COUNT(*) AS cnt FROM `sec-edgar-ralph.edgar.fact_filing_enriched`'
```

5. Run this report directly from BigQuery:

```bash
PYTHONPATH=src python -m edgar_report.main \
  --project sec-edgar-ralph \
  --dataset edgar \
  --table fact_filing_enriched \
  --location US \
  --year 2026 \
  --output output/edgar_s1_f1_report_2026.pdf
```

## Run with CSV (local proof-of-concept)

```bash
PYTHONPATH=src python -m edgar_report.main --from-csv sample/sample_filings.csv --output output/edgar_s1_f1_report_2026.pdf --year 2026
```

## AI analysis

- If `OPENAI_API_KEY` is set, analysis is generated via OpenAI chat completions REST API.
- Otherwise, a deterministic local fallback analysis is generated.

Optional env var:

```bash
export OPENAI_MODEL=gpt-4.1
```

## Troubleshooting merge-conflict syntax errors

If you resolved conflicts in GitHub and then see a Python parse error such as:

```text
SyntaxError: unmatched ']'
```

you likely have a malformed merge result in one of the source files.

1. Confirm there are no conflict markers left in the repo:

```bash
rg "^(<<<<<<<|=======|>>>>>>>)" src README.md scripts sample
```

2. Restore the known-good files from the latest commit if needed:

```bash
git checkout -- src/edgar_report/data.py src/edgar_report/main.py
```

3. Re-run a syntax check:

```bash
python -m compileall src
```

4. Run the report again:

```bash
PYTHONPATH=src python -m edgar_report.main --from-csv sample/sample_filings.csv --output output/edgar_s1_f1_report_2026.pdf --year 2026
```
