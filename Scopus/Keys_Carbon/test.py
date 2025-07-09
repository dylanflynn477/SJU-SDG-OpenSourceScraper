import requests
import os
from dotenv import load_dotenv

# Load API key
load_dotenv()
API_KEY = os.getenv("SCOPUS_API_KEY")

BASE_URL = "https://api.elsevier.com/content/search/scopus"
HEADERS = {
    "Accept": "application/json",
    "X-ELS-APIKey": API_KEY,
    "Content-Type": "application/x-www-form-urlencoded"
}

def test_scopus_query(issn: str, query: str, start_year: int = 2020, end_year: int = 2023):
    filter_query = f'ISSN({issn}) AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1} AND ({query})'
    payload = {
        'query': filter_query,
        'count': 0
    }

    use_post = len(filter_query) > 2000
    print(f"{'📮 POST' if use_post else '🔍 GET'} request with query length {len(filter_query)}")

    try:
        if use_post:
            response = requests.post(BASE_URL, headers=HEADERS, data=payload)
        else:
            response = requests.get(BASE_URL, headers=HEADERS, params=payload)

        print(f"Status Code: {response.status_code}")
        print("Response Preview:", response.text[:500])
        return response
    except Exception as e:
        print(f"❌ Exception occurred: {e}")
        return None

if __name__ == "__main__":
    issn = "0893-9454"
    with open("SDG01.txt", encoding="utf-8") as f:
        raw_query = f.read().replace("\n", " ").replace("\r", " ").strip()
        simplified_query = raw_query.replace("TITLE(", "TITLE-ABS-KEY(").replace("AUTHKEY(", "TITLE-ABS-KEY(")
    test_scopus_query(issn, simplified_query)
