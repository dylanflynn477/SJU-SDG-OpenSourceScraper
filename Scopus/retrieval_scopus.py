import requests
import os
from dotenv import load_dotenv
import pandas as pd
import time
from itertools import cycle
from typing import List, Dict, Tuple, Iterable, Set
from concurrent.futures import ProcessPoolExecutor, as_completed

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
) -> Tuple[int, bool, int, int]:
    """Return search results for ``query``.

    Returns a tuple ``(count, error, success_chars, error_chars)``. ``error`` is
    ``True`` if the query ultimately failed or needed patching. ``success_chars``
    and ``error_chars`` track the number of characters that were successfully
    processed versus those lost due to a 4xx/5xx error.
    """
    issn_filter = f'ISSN({issn.strip()})'
    filter_query = f'{issn_filter} AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1} AND ({query})'

    params = {
        'query': filter_query,
        'count': 0
    }

    if max_attempts is None:
        max_attempts = len(_multi_keys) * 3

    query_len = len(filter_query)

    try:
        # Queries are pre-split to avoid exceeding URL length limits
        response = requests.get(BASE_URL, headers=HEADERS, params=params)
        if response.status_code == 200:
            return (
                int(response.json()['search-results'].get('opensearch:totalResults', 0)),
                False,
                query_len,
                0,
            )
        elif response.status_code == 429:
            if attempts >= max_attempts:
                print("❌ Rate limit persists after multiple attempts.")
                return 0, True, 0, query_len
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
                succ_chars = 0
                err_chars = 0
                for part in parts:
                    c, e, s_c, f_c = query_scopus_count(part, issn, start_year, end_year, depth + 1)
                    total += c
                    succ_chars += s_c
                    err_chars += f_c
                    any_error = any_error or e
                return total, True, succ_chars, err_chars
            return 0, True, 0, query_len
    except Exception as e:
        print(f"❌ Error querying Scopus for ISSN '{issn}': {e}")
        return 0, True, 0, query_len

def query_scopus_eids(
    query: str,
    issn: str,
    start_year: int,
    end_year: int,
    depth: int = 0,
    attempts: int = 0,
    max_attempts: int | None = None,
) -> Tuple[Set[str], bool, int, int]:
    """Return the set of EIDs matching ``query`` for ``issn``."""
    issn_filter = f'ISSN({issn.strip()})'
    filter_query = f'{issn_filter} AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1} AND ({query})'

    params = {
        'query': filter_query,
        'field': 'eid',
        'count': 25,
        'start': 0,
    }

    if max_attempts is None:
        max_attempts = len(_multi_keys) * 3

    query_len = len(filter_query)
    eids: Set[str] = set()
    success_chars = 0
    error_chars = 0
    MAX_EIDS = 50000  # Cap how many EIDs we try to retrieve

    while True:
        try:
            response = requests.get(BASE_URL, headers=HEADERS, params=params)
            if response.status_code == 200:
                data = response.json().get('search-results', {})
                entries = data.get('entry', [])
                for entry in entries:
                    eid = entry.get('eid')
                    if eid:
                        eids.add(eid)

                success_chars += query_len
                total = int(data.get('opensearch:totalResults', 0))

                if len(eids) >= MAX_EIDS:
                    print(f"🔺 Reached EID cap of {MAX_EIDS}. Truncating results.")
                    break

                if params['start'] + len(entries) >= total or not entries:
                    break

                params['start'] += len(entries)
                time.sleep(1)  # Slight delay to reduce rate limit risk
                continue

            elif response.status_code == 429:
                if attempts >= max_attempts:
                    print("❌ Rate limit persists after multiple attempts.")
                    error_chars += query_len
                    return eids, True, success_chars, error_chars
                print("⚠️ Rate limit hit. Rotating key.")
                rotate_key()
                time.sleep(2)
                attempts += 1
                continue

            elif response.status_code == 400 and "Exceeds the maximum number allowed" in response.text:
                print("❌ Query too large for service level. Truncating.")
                error_chars += query_len
                return eids, True, success_chars, error_chars

            else:
                print(f"❌ Failed query ({response.status_code}) for ISSN: {issn}")
                print("Query preview:", filter_query[:300])
                print("Response:", response.text[:500])
                if depth < 2 and ' OR ' in query:
                    print("↪️ Attempting to split failed query further...")
                    parts = _split_query(query, max_len=max(len(query) // 2, 100))
                    union: Set[str] = set()
                    succ = 0
                    err = 0
                    any_error = False
                    for part in parts:
                        ids, e, s_c, f_c = query_scopus_eids(part, issn, start_year, end_year, depth + 1)
                        union.update(ids)
                        succ += s_c
                        err += f_c
                        any_error = any_error or e
                    eids.update(union)
                    success_chars += succ
                    error_chars += err
                    return eids, any_error, success_chars, error_chars
                error_chars += query_len
                return eids, True, success_chars, error_chars

        except Exception as e:
            print(f"❌ Error querying Scopus for ISSN '{issn}': {e}")
            error_chars += query_len
            return eids, True, success_chars, error_chars

    return eids, False, success_chars, error_chars

def query_total_articles(
    issn: str,
    start_year: int,
    end_year: int,
    attempts: int = 0,
    max_attempts: int | None = None,
) -> int:
    """Return the total number of articles for ``issn`` in the period."""
    filter_query = f'ISSN({issn.strip()}) AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1}'
    params = {'query': filter_query, 'count': 0}
    if max_attempts is None:
        max_attempts = len(_multi_keys) * 3

    while True:
        response = requests.get(BASE_URL, headers=HEADERS, params=params)
        if response.status_code == 200:
            return int(response.json()['search-results'].get('opensearch:totalResults', 0))
        elif response.status_code == 429:
            if attempts >= max_attempts:
                print("❌ Rate limit persists after multiple attempts.")
                return 0
            print("⚠️ Rate limit hit. Rotating key.")
            rotate_key()
            time.sleep(1)
            attempts += 1
            continue
        else:
            print(f"❌ Failed total count query ({response.status_code}) for ISSN: {issn}")
            print("Query preview:", filter_query[:300])
            print("Response:", response.text[:500])
            return 0

def process_journal_sdg_scores(issn, journal_name, sdg_queries, start_year, end_year):
    sdg_counts: Dict[int, int] = {}
    sdg_errors: Dict[int, int] = {}
    sdg_sets: Dict[int, Set[str]] = {}
    success_chars = 0
    error_chars = 0

    for sdg_id, parts in sdg_queries.items():
        eids: Set[str] = set()
        errors = 0
        for part in parts:
            ids, e, s_c, f_c = query_scopus_eids(part, issn, start_year, end_year)
            eids.update(ids)
            success_chars += s_c
            error_chars += f_c
            if e:
                errors += 1
        sdg_sets[sdg_id] = eids
        sdg_counts[sdg_id] = len(eids)
        sdg_errors[sdg_id] = errors

    total_articles = query_total_articles(issn, start_year, end_year)
    unique_sdg_articles = set().union(*sdg_sets.values()) if sdg_sets else set()

    if total_articles == 0:
        return None

    total_chars = success_chars + error_chars
    accuracy = (success_chars / total_chars) * 100 if total_chars else 0

    top_sdgs = sorted(sdg_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_total = sum(v for k, v in top_sdgs)
    top_dominance = (top_sdgs[0][1] / top_total) * 100 if top_total else 0
    sdg_presence = (len(unique_sdg_articles) / total_articles) * 100 if total_articles else 0
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
        "Error Summary": error_summary,
        "Accuracy (%)": round(accuracy, 2)
    }

def _process_single(issn: str, journal_name: str, sdg_queries: Dict[int, List[str]],
                   start_year: int, end_year: int) -> Dict[str, object] | None:
    """Helper to process a single journal entry."""
    print(f"🔍 Processing: {journal_name} ({issn})")
    return process_journal_sdg_scores(issn, journal_name, sdg_queries, start_year, end_year)


def process_all_journals(journals_csv: str, sdg_query_dir: str, output_csv: str,
                         start_year: int, end_year: int, num_workers: int = 1) -> None:
    """Process all journals in ``journals_csv``.

    If ``num_workers`` > 1, journals are processed in parallel using multiple
    processes. Parallel execution can speed up large datasets but may increase
    API usage rate.
    """
    sdg_queries = load_sdg_queries(sdg_query_dir)
    df = pd.read_csv(journals_csv)
    results = []

    try:
        if num_workers > 1:
            tasks: Iterable[tuple[str, str]] = [
                (row['ISSN'], row['Journal']) for _, row in df.iterrows()
            ]
            with ProcessPoolExecutor(max_workers=num_workers) as exe:
                future_map = {
                    exe.submit(_process_single, issn, name, sdg_queries, start_year, end_year):
                    (issn, name) for issn, name in tasks
                }
                for fut in as_completed(future_map):
                    res = fut.result()
                    if res:
                        results.append(res)
        else:
            for _, row in df.iterrows():
                res = _process_single(row['ISSN'], row['Journal'], sdg_queries, start_year, end_year)
                if res:
                    results.append(res)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user. Saving partial results...")
    finally:
        pd.DataFrame(results).to_csv(output_csv, index=False)
        print(f"✅ Results saved to '{output_csv}'")

if __name__ == "__main__":
    process_all_journals(
        journals_csv='journals.csv',
        sdg_query_dir='./Keys_2022',  # Folder with SDG01.txt, SDG02.txt, etc.
        output_csv='scopus_sdgii.csv',
        start_year=2020,
        end_year=2023,
        num_workers=4  # Increase this value to enable parallel processing
    )
