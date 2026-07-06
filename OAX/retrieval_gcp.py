import requests
import time
import re
import os
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# -------------------------------
# Google Sheets Configuration
# -------------------------------
load_dotenv()
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "service-account.json")
GOOGLE_SHEET_ID = os.getenv("OAX_GOOGLE_SHEET_ID")

if not GOOGLE_SHEET_ID:
    raise RuntimeError("Set OAX_GOOGLE_SHEET_ID in your environment or .env file")

# Authenticate with Google Sheets using the service account credentials
scopes = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
client = gspread.authorize(creds)

# Open the Google Sheet and get the first worksheet
sheet = client.open_by_key(GOOGLE_SHEET_ID)
worksheet = sheet.sheet1  # Assumes the first sheet is the target sheet

# ----------------------------------------
# OpenAlex API Functions
# ----------------------------------------

def reconstruct_abstract(abstract_inverted_index):
    if not abstract_inverted_index:
        return ''
    try:
        abstract_len = max([max(locs) for locs in abstract_inverted_index.values()]) + 1
    except ValueError:
        return ''
    abstract = [''] * abstract_len
    for term, positions in abstract_inverted_index.items():
        for pos in positions:
            if pos < abstract_len:
                abstract[pos] = term
    return ' '.join(abstract)

def get_works_for_issn(issn, start_year, end_year):
    base_url = 'https://api.openalex.org/works'
    params = {
        'filter': f'primary_location.source.issn:{issn},publication_year:{start_year}-{end_year},type:article',
        'per-page': 200,
        'select': 'title,abstract_inverted_index,publication_year,sustainable_development_goals,primary_location',
    }
    headers = {
        'User-Agent': 'YourAppName/1.0 (mailto:youremail@example.com)'
    }
    results = []
    cursor = '*'
    
    while True:
        params['cursor'] = cursor
        try:
            response = requests.get(base_url, params=params, headers=headers)
            if response.status_code != 200:
                print(f"Error fetching data: {response.status_code}")
                break
            data = response.json()
            for work in data.get('results', []):
                title = work.get('title', '')
                abstract = reconstruct_abstract(work.get('abstract_inverted_index'))
                sdgs = work.get('sustainable_development_goals', [])

                sdg_ids = [
                    int(re.findall(r'\d+', sdg.get('id', '').split('/')[-1])[0])
                    for sdg in sdgs if sdg.get('id') and re.findall(r'\d+', sdg.get('id', '').split('/')[-1])
                ]

                results.append({
                    'title': title,
                    'abstract': abstract,
                    'sdg_ids': "; ".join(map(str, sdg_ids))
                })

            cursor = data.get('meta', {}).get('next_cursor')
            if not cursor:
                break
            time.sleep(1)  # Avoid rate limiting
        except Exception as e:
            print(f"Error fetching works for ISSN {issn}: {e}")
            break
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

# -----------------------------------------------------------
# Read Data from Google Sheets
# -----------------------------------------------------------

def get_journal_data_from_google_sheet():
    """
    Reads journal names and ISSNs from the Google Sheet.
    """
    records = worksheet.get_all_values()
    if len(records) < 2:
        print("No journal data found in Google Sheet.")
        return []

    # Convert to a DataFrame
    df = pd.DataFrame(records[1:], columns=records[0])  # First row as headers

    return df[['Journal', 'ISSN']].dropna().to_dict(orient='records')

# -----------------------------------------------------------
# Update Google Sheets with Results
# -----------------------------------------------------------

def update_google_sheet_with_results(results):
    """
    Updates the Google Sheet with the processed SDGII scores.
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

# -----------------------------------------------------------
# Main Processing Function
# -----------------------------------------------------------

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
            articles_data = get_works_for_issn(issn, start_year, end_year)
            
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

# -----------------------------------------------------------
# Main Execution
# -----------------------------------------------------------

if __name__ == "__main__":
    start_year = 2020  # Start year for fetching articles
    end_year = 2023    # End year for fetching articles

    process_all_journals(start_year, end_year)
