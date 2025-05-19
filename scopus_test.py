import requests
import time
import re
import os
import pandas as pd
from dotenv import load_dotenv

# ----------------------------------------
# Environment Setup
# ----------------------------------------
load_dotenv()
SCOPUS_API_KEY = os.getenv("SCOPUS_API_KEY")  # Your Elsevier Scopus API key

# ----------------------------------------
# Scopus API Functions
# ----------------------------------------

def get_works_for_issn_scopus(issn, start_year, end_year):
    base_url = "https://api.elsevier.com/content/search/scopus"
    headers = {
        "X-ELS-APIKey": SCOPUS_API_KEY,
        "Accept": "application/json"
    }
    
    query = f"ISSN({issn}) AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1} AND DOCTYPE(ar)"
    count = 25
    start = 0
    results = []

    while True:
        params = {
            "query": query,
            "count": count,
            "start": start
        }
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"Error fetching data from Scopus for ISSN {issn}: {response.status_code}")
            break
        
        data = response.json()
        entries = data.get("search-results", {}).get("entry", [])
        if not entries:
            break
        
        for entry in entries:
            title = entry.get("dc:title", "")
            abstract = entry.get("dc:description", "")
            sdgs_data = entry.get("sdgs", [])
            
            if sdgs_data:
                sdg_ids = []
                for sdg in sdgs_data:
                    sdg_id_str = sdg.get("id", "")
                    found = re.findall(r'\d+', sdg_id_str)
                    if found:
                        sdg_ids.append(found[0])
            else:
                sdg_ids = []
            
            results.append({
                "title": title,
                "abstract": abstract,
                "sdg_ids": "; ".join(sdg_ids)
            })

        total_results = int(data.get("search-results", {}).get("opensearch:totalResults", "0"))
        start += count
        if start >= total_results:
            break
        
        time.sleep(1)

    return results

def calculate_sdgi_score(df):
    total_articles = len(df)
    sdg_column = df['sdg_ids'].dropna()
    articles_with_sdg = sdg_column[sdg_column != ""].count()
    sdg_presence = (articles_with_sdg / total_articles) * 100 if total_articles > 0 else 0

    sdg_exploded = sdg_column.str.split("; ").explode()
    sdg_exploded = sdg_exploded[sdg_exploded != '']
    sdg_counts = sdg_exploded.value_counts()

    if not sdg_counts.empty:
        top_sdgs = sdg_counts.head(3)
        top_sdg_total = top_sdgs.sum()
        top_sdg_dominance = (top_sdgs.iloc[0] / top_sdg_total) * 100 if top_sdg_total > 0 else 0
        top_sdg_ids = list(top_sdgs.index) + ["Unknown"] * (3 - len(top_sdgs))
    else:
        top_sdg_dominance = 0
        top_sdg_ids = ["Unknown", "Unknown", "Unknown"]
    
    sdgii_score = (0.5 * sdg_presence) + (0.5 * top_sdg_dominance)

    return {
        "Total Articles": total_articles,
        "SDG Presence (%)": round(sdg_presence, 2),
        "Top SDG Dominance (%)": round(top_sdg_dominance, 2),
        "SDGII Score (%)": round(sdgii_score, 2),
        "Top SDG 1": top_sdg_ids[0],
        "Top SDG 2": top_sdg_ids[1],
        "Top SDG 3": top_sdg_ids[2]
    }

# ----------------------------------------
# Main Execution for a Single Journal
# ----------------------------------------

if __name__ == "__main__":
    journal_name = "Academy of Management"   # You can change this
    issn = "0001-4273"                  # Example ISSN for "Renewable Energy"
    start_year = 2020
    end_year = 2023

    print(f"Fetching SDG data for '{journal_name}' (ISSN: {issn}) from {start_year} to {end_year}...")
    articles_data = get_works_for_issn_scopus(issn, start_year, end_year)
    
    if articles_data:
        df = pd.DataFrame(articles_data)
        scores = calculate_sdgi_score(df)
        scores.update({"Journal": journal_name, "ISSN": issn})
        print("\n--- SDG Impact Summary ---")
        for k, v in scores.items():
            print(f"{k}: {v}")
    else:
        print("No articles found or error occurred.")
