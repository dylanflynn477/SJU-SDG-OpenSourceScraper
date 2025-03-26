import requests
import time
import re
import os
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# ----------------------------------------
# Environment and Google Sheets Setup
# ----------------------------------------
load_dotenv()
SCOPUS_API_KEY = os.getenv("SCOPUS_API_KEY")  # Your Elsevier Scopus API key

# Google Sheets configuration – update these if necessary
GOOGLE_CREDENTIALS_FILE = 'weighty-archive-449420-v8-1c9c00e21ff3.json'
GOOGLE_SHEET_ID = '1aWF15o4pjWOLesg6y-sLUvDrTiRtzBiSqeiYxaWZjDo'

# Authenticate with Google Sheets
scopes = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
client = gspread.authorize(creds)
worksheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1  # Uses the first worksheet

# ----------------------------------------
# Scopus API Functions
# ----------------------------------------

def get_works_for_issn_scopus(issn, start_year, end_year):
    """
    Fetch works for a given ISSN from Scopus API within the specified publication years.
    
    Note: This function assumes that the Scopus API response includes a field "sdgs"
    containing the SDG mapping data (each with an "id" field). Adjust the query and parsing
    as needed based on your actual API response.
    """
    base_url = "https://api.elsevier.com/content/search/scopus"
    headers = {
        "X-ELS-APIKey": SCOPUS_API_KEY,
        "Accept": "application/json"
    }
    
    # Build the query: look for articles (DOCTYPE(ar)) from the journal with the specified ISSN
    # and within the given publication year range.
    query = f"ISSN({issn}) AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1} AND DOCTYPE(ar)"
    count = 25  # Maximum number of results per page (per Scopus API limits)
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
        search_results = data.get("search-results", {})
        entries = search_results.get("entry", [])
        if not entries:
            break
        
        for entry in entries:
            # Extract title (field names follow Scopus conventions)
            title = entry.get("dc:title", "")
            # Extract abstract if available (may not be present in search results)
            abstract = entry.get("dc:description", "")
            
            # Extract SDG mapping data – assuming a field "sdgs" exists
            sdgs_data = entry.get("sdgs", [])
            if sdgs_data:
                sdg_ids = []
                for sdg in sdgs_data:
                    # Assume each sdg has an "id" like "SDG 1" or similar
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
        
        # Pagination: Scopus returns the total number of results in "opensearch:totalResults"
        total_results = int(search_results.get("opensearch:totalResults", "0"))
        start += count
        if start >= total_results:
            break
        
        time.sleep(1)  # Pause to avoid rate limiting
    
    return results

def calculate_sdgi_score(df):
    """
    Calculate SDG Impact Index (SDGII) scores based on the proportion of articles with SDG labels
    and the dominance of the top SDG in the journal's articles.
    """
    total_articles = len(df)
    sdg_column = df['sdg_ids'].dropna()
    
    articles_with_sdg = sdg_column[sdg_column != ""].count()
    sdg_presence = (articles_with_sdg / total_articles) * 100 if total_articles > 0 else 0
    
    # Split and count individual SDG IDs
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
# Google Sheets Data Functions
# ----------------------------------------

def get_journal_data_from_google_sheet():
    """
    Reads journal names and ISSNs from the Google Sheet.
    The sheet should have headers with at least "Journal" and "ISSN".
    """
    records = worksheet.get_all_values()
    if len(records) < 2:
        print("No journal data found in Google Sheet.")
        return []
    
    df = pd.DataFrame(records[1:], columns=records[0])
    return df[['Journal', 'ISSN']].dropna().to_dict(orient='records')

def update_google_sheet_with_results(results):
    """
    Updates the Google Sheet with the computed SDGII scores.
    """
    header = ["Journal", "ISSN", "Total Articles", "SDG Presence (%)", 
              "Top SDG Dominance (%)", "SDGII Score (%)", "Top SDG 1", "Top SDG 2", "Top SDG 3"]
    
    data = [header] + [[
        result.get("Journal", ""),
        result.get("ISSN", ""),
        result.get("Total Articles", ""),
        result.get("SDG Presence (%)", ""),
        result.get("Top SDG Dominance (%)", ""),
        result.get("SDGII Score (%)", ""),
        result.get("Top SDG 1", ""),
        result.get("Top SDG 2", ""),
        result.get("Top SDG 3", "")
    ] for result in results]
    
    worksheet.update('A1', data)
    print("Results have been successfully updated in Google Sheets.")

# ----------------------------------------
# Main Processing Function
# ----------------------------------------

def process_all_journals(start_year, end_year):
    journal_data = get_journal_data_from_google_sheet()
    if not journal_data:
        print("No journal data to process.")
        return
    
    results = []
    for journal in journal_data:
        issn = journal.get('ISSN')
        journal_name = journal.get('Journal')
        if issn and journal_name:
            print(f"Processing journal '{journal_name}' (ISSN: {issn})...")
            articles_data = get_works_for_issn_scopus(issn, start_year, end_year)
            if articles_data:
                df = pd.DataFrame(articles_data)
                sdgi_scores = calculate_sdgi_score(df)
                sdgi_scores.update({
                    "Journal": journal_name,
                    "ISSN": issn
                })
                results.append(sdgi_scores)
            else:
                print(f"No data found for '{journal_name}'.")
    
    if results:
        update_google_sheet_with_results(results)
    else:
        print("No results to update.")

# ----------------------------------------
# Main Execution
# ----------------------------------------

if __name__ == "__main__":
    start_year = 2020  # Define the start year for fetching articles
    end_year = 2023    # Define the end year for fetching articles
    process_all_journals(start_year, end_year)
