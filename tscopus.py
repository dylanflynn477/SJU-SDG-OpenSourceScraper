import requests
import os
from dotenv import load_dotenv
import time

# Load API key from .env
load_dotenv()
API_KEY = os.getenv("SCOPUS_API_KEY")

# Example EID
EID = "2-s2.0-85173784823"

# API endpoint
url = f"https://api.elsevier.com/content/abstract/eid/{EID}"

# Headers
headers = {
    "Accept": "application/json",
    "X-ELS-APIKey": API_KEY,
    "X-ELS-ResourceVersion": "latest"
}

# Request
response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    record = data.get("abstracts-retrieval-response", {})

    # ---------------------
    # ✅ METADATA
    # ---------------------
    print("📄 Metadata")
    title = record.get("coredata", {}).get("dc:title", "N/A")
    doi = record.get("coredata", {}).get("prism:doi", "N/A")
    pub_year = record.get("coredata", {}).get("prism:coverDate", "N/A").split("-")[0]
    journal = record.get("coredata", {}).get("prism:publicationName", "N/A")

    authors = record.get("authors", {}).get("author", [])
    author_list = []
    for a in authors:
        name = f"{a.get('ce:given-name', '')} {a.get('ce:surname', '')}".strip()
        if name:
            author_list.append(name)
    author_str = ", ".join(author_list) if author_list else "N/A"

    print(f"Title     : {title}")
    print(f"Authors   : {author_str}")
    print(f"Journal   : {journal}")
    print(f"DOI       : {doi}")
    print(f"Year      : {pub_year}")

    # ---------------------
    # ✅ SDGs
    # ---------------------
    print("\n🌍 SDG Classifications")
    sdg_data = record.get('item', {}).get('xocs:meta', {}).get('xocs:sdg-terms', {}).get('xocs:sdg-term', [])

    if isinstance(sdg_data, list) and sdg_data:
        for sdg in sdg_data:
            print(f"- {sdg.get('$')}")
    else:
        print("⚠️ No SDGs found for this document.")
        time.sleep(2.0)
        print(data)

else:
    print(f"❌ Failed to retrieve data. HTTP Status: {response.status_code}")
