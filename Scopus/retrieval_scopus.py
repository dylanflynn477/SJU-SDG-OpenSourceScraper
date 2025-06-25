import requests
import os
from dotenv import load_dotenv
import pandas as pd
import time
import re

# Load API key
load_dotenv()
API_KEY = os.getenv("SCOPUS_API_KEY")

BASE_URL = "https://api.elsevier.com/content/search/scopus"

HEADERS = {
    "Accept": "application/json",
    "X-ELS-APIKey": API_KEY,
    "Content-Type": "application/x-www-form-urlencoded"
}

def load_sdg_queries(directory):
    queries = {}
    for fname in os.listdir(directory):
        if fname.endswith(".txt") and fname.startswith("SDG"):
            sdg_id = int(fname[3:5])
            with open(os.path.join(directory, fname), 'r', encoding='utf-8') as f:
                raw = f.read().replace('\n', ' ').replace('\r', ' ').strip()
                simplified = raw.replace("TITLE(", "TITLE-ABS-KEY(").replace("AUTHKEY(", "TITLE-ABS-KEY(")
                queries[sdg_id] = simplified
    return queries


def split_query(query, max_length=1800):
    """Split very long query strings into smaller segments.

    The Scopus API rejects extremely long queries. This function attempts to
    break a long OR-based query into chunks that are under ``max_length``
    characters. The splitting is naive and assumes the top-level structure of
    the query is a series of clauses joined by ``OR``.
    """
    cleaned = query.strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1]

    tokens = cleaned.split(") OR (")
    segments = []
    current = ""
    for tok in tokens:
        tok = tok.strip()
        if not current:
            current = tok
            continue

        candidate = current + ") OR (" + tok
        if len(candidate) > max_length:
            segments.append(f"({current})")
            current = tok
        else:
            current = candidate

    if current:
        segments.append(f"({current})")

    return segments

def query_scopus_count(query, journal_name, start_year, end_year):
    """Return the number of search results for the given query."""

    segments = split_query(query)
    total = 0

    for segment in segments:
        journal_quoted = f'SRCTITLE("{journal_name.strip()}")'
        filter_query = f'{journal_quoted} AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1} AND {segment}'

        params = {
            'query': filter_query,
            'count': 0
        }

        try:
            if len(filter_query) > 2000:
                response = requests.post(BASE_URL, headers=HEADERS, data=params)
            else:
                response = requests.get(BASE_URL, headers=HEADERS, params=params)

            if response.status_code == 200:
                total += int(response.json()['search-results'].get('opensearch:totalResults', 0))
            elif response.status_code == 429:
                print("⚠️ Rate limit hit. Sleeping 10s.")
                time.sleep(10)
                total += query_scopus_count(segment, journal_name, start_year, end_year)
            else:
                print(f"❌ Failed query ({response.status_code}) for journal: {journal_name}")
                print("Query preview:", filter_query[:300])
                print("Response:", response.text[:500])
        except Exception as e:
            print(f"❌ Error querying Scopus for journal '{journal_name}': {e}")

    return total

def process_journal_sdg_scores(issn, journal_name, sdg_queries, start_year, end_year):
    sdg_counts = {}
    total_articles = 0
    for sdg_id, query in sdg_queries.items():
        count = query_scopus_count(query, journal_name, start_year, end_year)
        sdg_counts[sdg_id] = count
        total_articles += count

    if total_articles == 0:
        return None

    top_sdgs = sorted(sdg_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_total = sum(v for k, v in top_sdgs)
    top_dominance = (top_sdgs[0][1] / top_total) * 100 if top_total else 0
    sdg_presence = (len([v for v in sdg_counts.values() if v > 0]) / 17) * 100
    sdgii_score = 0.5 * sdg_presence + 0.5 * top_dominance

    return {
        "Journal": journal_name,
        "ISSN": issn,
        "Total Articles": total_articles,
        "SDG Presence (%)": round(sdg_presence, 2),
        "Top SDG Dominance (%)": round(top_dominance, 2),
        "SDGII Score (%)": round(sdgii_score, 2),
        "Top SDG 1": top_sdgs[0][0] if len(top_sdgs) > 0 else "N/A",
        "Top SDG 2": top_sdgs[1][0] if len(top_sdgs) > 1 else "N/A",
        "Top SDG 3": top_sdgs[2][0] if len(top_sdgs) > 2 else "N/A"
    }

def process_all_journals(journals_csv, sdg_query_dir, output_csv, start_year, end_year):
    sdg_queries = load_sdg_queries(sdg_query_dir)
    df = pd.read_csv(journals_csv)
    results = []
    for _, row in df.iterrows():
        issn = row['ISSN']
        journal_name = row['Journal']
        print(f"🔍 Processing: {journal_name} ({issn})")
        result = process_journal_sdg_scores(issn, journal_name, sdg_queries, start_year, end_year)
        if result:
            results.append(result)

    pd.DataFrame(results).to_csv(output_csv, index=False)
    print(f"✅ All results saved to '{output_csv}'")

if __name__ == "__main__":
    process_all_journals(
        journals_csv='journals.csv',
        sdg_query_dir='./Keys',  # Folder with SDG01.txt, SDG03.txt, etc.
        output_csv='scopus_sdgii.csv',
        start_year=2020,
        end_year=2023
    )
