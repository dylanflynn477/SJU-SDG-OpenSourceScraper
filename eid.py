import requests
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("SCOPUS_API_KEY")

def get_eids_for_journal(issn, count=5):
    url = "https://api.elsevier.com/content/search/scopus"
    headers = {
        "X-ELS-APIKey": API_KEY,
        "Accept": "application/json"
    }
    params = {
        "query": f"ISSN({issn}) AND DOCTYPE(ar)",  # Only articles
        "count": count,
        "sort": "pubyear desc"
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print("Failed to retrieve data:", response.status_code)
        print(response.text)
        return []

    results = response.json().get("search-results", {}).get("entry", [])
    for entry in results:
        print("Title:", entry.get("dc:title"))
        print("EID:", entry.get("eid"))
        print("Publication Year:", entry.get("prism:coverDate", "N/A").split("-")[0])
        print("-" * 60)

# Run the function
get_eids_for_journal("0001-4273")
