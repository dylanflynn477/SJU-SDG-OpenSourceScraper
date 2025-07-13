import requests
import os
import pandas as pd
import time
from dotenv import load_dotenv
from itertools import cycle

# Load API keys
load_dotenv()
_keys = [k.strip() for k in os.getenv("SCOPUS_API_KEYS", "").split(",") if k.strip()]
if not _keys:
    single = os.getenv("SCOPUS_API_KEY")
    if single:
        _keys = [single]
    else:
        raise RuntimeError("No SCOPUS_API_KEY or SCOPUS_API_KEYS provided")

key_cycle = cycle(_keys)
current_key = next(key_cycle)

BASE_URL = "https://api.elsevier.com/content/search/scopus"
HEADERS = {
    "Accept": "application/json",
    "X-ELS-APIKey": current_key,
    "Content-Type": "application/json"
}

def rotate_key():
    global current_key
    current_key = next(key_cycle)
    HEADERS["X-ELS-APIKey"] = current_key

def get_citations_for_journal(issn, start_year=2016, end_year=2019, max_results=50000):
    eids = []
    citations = []
    start = 0
    while True:
        query = f'ISSN({issn}) AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1}'
        params = {
            'query': query,
            'field': 'eid,citedby-count',
            'count': 25,
            'start': start
        }

        resp = requests.get(BASE_URL, headers=HEADERS, params=params)
        if resp.status_code == 429:
            rotate_key()
            time.sleep(1)
            continue
        elif resp.status_code != 200:
            print(f"Error {resp.status_code} for ISSN {issn}")
            break

        data = resp.json().get('search-results', {})
        entries = data.get('entry', [])
        if not entries:
            break

        for entry in entries:
            try:
                citations.append(int(entry.get('citedby-count', 0)))
            except:
                continue

        start += len(entries)
        if start >= int(data.get('opensearch:totalResults', 0)) or start >= max_results:
            break

        time.sleep(1)

    return citations

def compute_avg_citations(csv_path):
    df = pd.read_csv(csv_path)
    results = []

    for _, row in df.iterrows():
        issn = row.get('ISSN')
        journal = row.get('Journal', 'Unknown')
        print(f"🔍 Fetching for {journal} ({issn})")
        citations = get_citations_for_journal(issn)
        total = sum(citations)
        count = len(citations)
        avg = round(total / count, 2) if count > 0 else 0
        results.append({
            'Journal': journal,
            'ISSN': issn,
            'Articles Found': count,
            'Total Citations': total,
            'Average Citations per Article': avg
        })

    out_df = pd.DataFrame(results)
    out_df.to_csv("journal_avg_citations_2016_2019.csv", index=False)
    print("✅ Done. Results saved to journal_avg_citations.csv")

if __name__ == "__main__":
    compute_avg_citations("journals100.csv")
