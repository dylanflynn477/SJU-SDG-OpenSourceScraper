import requests
import os
from dotenv import load_dotenv
import pandas as pd
import time
from itertools import cycle
from typing import List, Dict, Tuple

# Load API keys (comma separated) or fallback to single key
load_dotenv()
_multi_keys = [k.strip() for k in os.getenv("SCOPUS_API_KEYS", "").split(",") if k.strip()]
if not _multi_keys:
    single = os.getenv("SCOPUS_API_KEY")
    if single:
        _multi_keys = [single]
    else:
        raise RuntimeError("No SCOPUS_API_KEY or SCOPUS_API_KEYS provided")

_api_cycle = cycle(_multi_keys)
_current_key = next(_api_cycle)

BASE_URL = "https://api.elsevier.com/content/search/scopus"

HEADERS = {
    "Accept": "application/json",
    "X-ELS-APIKey": _current_key,
    "Content-Type": "application/x-www-form-urlencoded"
}

def rotate_key() -> None:
    """Switch to the next API key in the cycle."""
    global _current_key
    _current_key = next(_api_cycle)
    HEADERS["X-ELS-APIKey"] = _current_key

def _split_query(query: str, max_len: int = 1800) -> List[str]:
    """Split a long Scopus query into balanced chunks under ``max_len`` characters."""
    tokens = query.split(' OR ')
    parts: List[str] = []
    current = tokens[0]
    diff = current.count('(') - current.count(')')
    for tok in tokens[1:]:
        candidate = f"{current} OR {tok}"
        if len(candidate) <= max_len:
            current = candidate
            diff += tok.count('(') - tok.count(')')
        else:
            if diff > 0:
                current += ')' * diff
                tok = '(' * diff + tok
            elif diff < 0:
                current = '(' * (-diff) + current
            parts.append(current)
            current = tok
            diff = tok.count('(') - tok.count(')')
    if diff > 0:
        current += ')' * diff
    elif diff < 0:
        current = '(' * (-diff) + current
    parts.append(current)
    return parts


def load_sdg_queries(directory: str) -> Dict[int, List[str]]:
    queries: Dict[int, List[str]] = {}
    for fname in os.listdir(directory):
        if fname.endswith(".txt") and fname.startswith("SDG"):
            sdg_id = int(fname[3:5])
            with open(os.path.join(directory, fname), 'r', encoding='utf-8') as f:
                raw = f.read().replace('\n', ' ').replace('\r', ' ').strip()
                simplified = raw.replace("TITLE(", "TITLE-ABS-KEY(").replace("AUTHKEY(", "TITLE-ABS-KEY(")
                queries[sdg_id] = _split_query(simplified)
    return queries

def query_scopus_count(
    query: str,
    issn: str,
    start_year: int,
    end_year: int,
    depth: int = 0,
    attempts: int = 0,
    max_attempts: int | None = None,
) -> Tuple[int, bool]:
    """Return the number of search results for the given query.

    Returns a tuple ``(count, error)`` where ``error`` is ``True`` if the query
    failed and had to be patched or ultimately returned no results due to an
    error condition.
    """
    issn_filter = f'ISSN({issn.strip()})'
    filter_query = f'{issn_filter} AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1} AND ({query})'

    params = {
        'query': filter_query,
        'count': 0
    }

    if max_attempts is None:
        max_attempts = len(_multi_keys) * 3

    try:
        # Queries are pre-split to avoid exceeding URL length limits
        response = requests.get(BASE_URL, headers=HEADERS, params=params)
        if response.status_code == 200:
            return int(response.json()['search-results'].get('opensearch:totalResults', 0)), False
        elif response.status_code == 429:
            if attempts >= max_attempts:
                print("❌ Rate limit persists after multiple attempts.")
                return 0, True
            print("⚠️ Rate limit hit. Rotating key.")
            rotate_key()
            time.sleep(1)
            return query_scopus_count(query, issn, start_year, end_year, depth, attempts + 1, max_attempts)
        else:
            print(f"❌ Failed query ({response.status_code}) for ISSN: {issn}")
            print("Query preview:", filter_query[:300])
            print("Response:", response.text[:500])
            # Attempt to further split the query if possible
            if depth < 2 and ' OR ' in query:
                print("↪️ Attempting to split failed query further...")
                parts = _split_query(query, max_len=max(len(query) // 2, 100))
                total = 0
                any_error = False
                for part in parts:
                    c, e = query_scopus_count(part, issn, start_year, end_year, depth + 1)
                    total += c
                    any_error = any_error or e
                return total, True
            return 0, True
    except Exception as e:
        print(f"❌ Error querying Scopus for ISSN '{issn}': {e}")
        return 0, True

def process_journal_sdg_scores(issn, journal_name, sdg_queries, start_year, end_year):
    sdg_counts = {}
    sdg_errors = {}
    total_articles = 0
    for sdg_id, parts in sdg_queries.items():
        count = 0
        errors = 0
        for part in parts:
            c, e = query_scopus_count(part, issn, start_year, end_year)
            count += c
            if e:
                errors += 1
        sdg_counts[sdg_id] = count
        sdg_errors[sdg_id] = errors
        total_articles += count

    if total_articles == 0:
        return None

    top_sdgs = sorted(sdg_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_total = sum(v for k, v in top_sdgs)
    top_dominance = (top_sdgs[0][1] / top_total) * 100 if top_total else 0
    sdg_presence = (len([v for v in sdg_counts.values() if v > 0]) / 17) * 100
    sdgii_score = 0.5 * sdg_presence + 0.5 * top_dominance

    error_summary = "; ".join(
        f"SDG{sdg_id:02d}:{errors}" for sdg_id, errors in sdg_errors.items() if errors
    )

    return {
        "Journal": journal_name,
        "ISSN": issn,
        "Total Articles": total_articles,
        "SDG Presence (%)": round(sdg_presence, 2),
        "Top SDG Dominance (%)": round(top_dominance, 2),
        "SDGII Score (%)": round(sdgii_score, 2),
        "Top SDG 1": top_sdgs[0][0] if len(top_sdgs) > 0 else "N/A",
        "Top SDG 2": top_sdgs[1][0] if len(top_sdgs) > 1 else "N/A",
        "Top SDG 3": top_sdgs[2][0] if len(top_sdgs) > 2 else "N/A",
        "Error Summary": error_summary
    }

def process_all_journals(journals_csv, sdg_query_dir, output_csv, start_year, end_year):
    sdg_queries = load_sdg_queries(sdg_query_dir)
    df = pd.read_csv(journals_csv)
    results = []
    try:
        for _, row in df.iterrows():
            issn = row['ISSN']
            journal_name = row['Journal']
            print(f"🔍 Processing: {journal_name} ({issn})")
            result = process_journal_sdg_scores(issn, journal_name, sdg_queries, start_year, end_year)
            if result:
                results.append(result)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user. Saving partial results...")
    finally:
        pd.DataFrame(results).to_csv(output_csv, index=False)
        print(f"✅ Results saved to '{output_csv}'")

if __name__ == "__main__":
    process_all_journals(
        journals_csv='journals.csv',
        sdg_query_dir='./Keys',  # Folder with SDG01.txt, SDG02.txt, etc.
        output_csv='scopus_sdgii.csv',
        start_year=2020,
        end_year=2023
    )
