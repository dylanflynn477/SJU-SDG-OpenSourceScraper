import requests
import os
from dotenv import load_dotenv

# Load your Scopus API key from environment variables
load_dotenv()
API_KEY = os.getenv("SCOPUS_API_KEY")

def search_article_by_title(title):
    url = "https://api.elsevier.com/content/search/scopus"
    headers = {
        "X-ELS-APIKey": API_KEY,
        "Accept": "application/json"
    }
    params = {
        "query": f'TITLE("{title}")',
        "count": 1
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        results = response.json().get("search-results", {}).get("entry", [])
        if results:
            for entry in results:
                print("Title:", entry.get("dc:title"))
                print("EID:", entry.get("eid"))
                print("DOI:", entry.get("prism:doi", "N/A"))
                print("Publication Year:", entry.get("prism:coverDate", "N/A").split("-")[0])
                print("-" * 60)
        else:
            print("No results found.")
    else:
        print(f"Error: {response.status_code}")

# Replace with your article title
article_title = "Inequalities in democratic worker-owned firms by gender, race and immigration status: evidence from the first national survey of the sector"
search_article_by_title(article_title)
