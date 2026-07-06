# SJU OAX Research Automation

This repository contains Python scripts and spreadsheet templates used to automate bibliometric research workflows for an academic impact/scoring project. The project is no longer active, but the code is preserved as a portfolio/archive artifact.

## What It Does

- Retrieves publication metadata by journal ISSN from OpenAlex, Scopus, Dimensions exports, and RRBM reports.
- Scores journal/article sets against Sustainable Development Goal (SDG) keyword mappings.
- Calculates SDG presence, top-SDG dominance, SDGII-style scores, citation summaries, and an experimental R2 score.
- Handles large Scopus keyword queries by splitting them into smaller requests and rotating API keys when rate limits are hit.
- Produces CSV or Google Sheets outputs for downstream review.

## Repository Layout

- `OAX/` - OpenAlex retrieval and SDG scoring scripts.
- `Scopus/` - Scopus retrieval, citation, SDG keyword, and prototype scripts.
- `Dimensions/` - Dimensions CSV/XLSX processing scripts and workbook templates.
- `RRBM/` - RRBM report download and Google Sheets upload automation.

## Requirements

Python 3.10+ is recommended.

Install the common dependencies with:

```bash
pip install -r requirements.txt
```

Some workflows require external credentials or browser automation:

- Scopus scripts require an Elsevier/Scopus API key.
- Google Sheets workflows require a Google service-account JSON file.
- RRBM automation requires RRBM credentials and Chrome/ChromeDriver support.

## Configuration

Copy `.env.example` to `.env` and fill in only the values needed for the workflow you plan to run.

```bash
cp .env.example .env
```

Expected variables include:

- `SCOPUS_API_KEY` or `SCOPUS_API_KEYS`
- `GOOGLE_CREDENTIALS_FILE`
- `OAX_GOOGLE_SHEET_ID`
- `SCOPUS_GOOGLE_SHEET_ID`
- `RRBM_GOOGLE_SHEET_ID`
- `RRBM_SHEET_NAME`
- `RRBM_USERNAME`
- `RRBM_PASSWORD`

Credential files, local CSV exports, generated outputs, and `.env` files are intentionally ignored by Git.

## Example Workflows

Run OpenAlex scoring for journals listed in a CSV:

```bash
python OAX/retrieval_v3.py
```

Run Scopus SDG scoring:

```bash
python Scopus/retrieval_scopus.py
```

Process Dimensions exports:

```bash
python Dimensions/retrieval_dimensions_csv.py
```

These scripts were built for a specific research workflow, so file names such as `journals.csv`, `alabama.csv`, or year folders may need to be adjusted before reuse.

## Status

Archived. This repository is published to show the project shape and implementation approach, not as a maintained package.

## Notes

- The SDG keyword files are large because they preserve full query expressions used by the retrieval scripts.
- API responses and generated datasets are not committed.
- Spreadsheet files are retained as lightweight templates/examples for the original workflow.
