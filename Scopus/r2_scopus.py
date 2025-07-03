import pandas as pd
import os
from dotenv import load_dotenv
from retrieval_scopus import (
    load_sdg_queries,
    process_journal_sdg_scores,
    HEADERS,
    rotate_key,
    _multi_keys,
)
import requests
import time

# === CONFIG ===
SDG_QUERY_DIR = './Keys'  # Folder containing SDG01.txt, ..., SDG17.txt
INPUT_CSV = 'journals.csv'  # CSV with columns: Journal, ISSN
OUTPUT_CSV = 'r2_output.csv'
START_YEAR = 2020
END_YEAR = 2024

# === SETUP ===
load_dotenv()
# HEADERS and rotate_key imported from retrieval_scopus

BASE_URL = "https://api.elsevier.com/content/search/scopus"

def get_total_and_average_citations(issn, start_year, end_year, attempts=0, max_attempts=None):
    """Query Scopus for total and average citations for a journal."""
    query = f'ISSN({issn}) AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1}'
    params = {'query': query, 'count': 25}  # Fetch up to 25 articles for sample averaging

    if max_attempts is None:
        max_attempts = len(_multi_keys) * 3

    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=params)
        if response.status_code == 200:
            entries = response.json().get('search-results', {}).get('entry', [])
            citation_counts = [int(e.get('citedby-count', 0)) for e in entries if 'citedby-count' in e]
            total = sum(citation_counts)
            avg = (total / len(citation_counts)) if citation_counts else 0
            return total, avg
        elif response.status_code == 429:
            if attempts >= max_attempts:
                print("❌ Rate limit persists after multiple attempts.")
                return 0, 0
            print("⚠️ Rate limit hit. Rotating key.")
            rotate_key()
            time.sleep(1)
            return get_total_and_average_citations(issn, start_year, end_year, attempts + 1, max_attempts)
        else:
            print(f"❌ Citation query failed for {issn}: {response.status_code}")
            return 0, 0
    except Exception as e:
        print(f"❌ Error during citation fetch for {issn}: {e}")
        return 0, 0

def compute_r2(journal_row, sdg_queries):
    issn = journal_row['ISSN']
    name = journal_row['Journal']
    print(f"🔍 Processing {name} ({issn})")

    # SDGII calculation
    sdg_data = process_journal_sdg_scores(issn, name, sdg_queries, START_YEAR, END_YEAR)
    if sdg_data is None:
        return None

    # Citation data
    total_cites, avg_cites = get_total_and_average_citations(issn, START_YEAR, END_YEAR)

    # R² score
    r2 = 0.5 * avg_cites * (sdg_data['SDGII Score (%)'] / 100)

    return {
        "Journal": name,
        "ISSN": issn,
        "SDGII (%)": sdg_data['SDGII Score (%)'],
        "Top SDG 1": sdg_data['Top SDG 1'],
        "Top SDG 2": sdg_data['Top SDG 2'],
        "Top SDG 3": sdg_data['Top SDG 3'],
        "Total Citations": total_cites,
        "Avg Citations": round(avg_cites, 2),
        "R² Score": round(r2, 2)
    }

def main():
    sdg_queries = load_sdg_queries(SDG_QUERY_DIR)
    journals = pd.read_csv(INPUT_CSV)
    results = []

    try:
        for _, row in journals.iterrows():
            result = compute_r2(row, sdg_queries)
            if result:
                results.append(result)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user. Saving partial results...")
    finally:
        df = pd.DataFrame(results)
        df.to_csv(OUTPUT_CSV, index=False)
        print(f"✅ R² data saved to {OUTPUT_CSV}")

if __name__ == '__main__':
    main()
