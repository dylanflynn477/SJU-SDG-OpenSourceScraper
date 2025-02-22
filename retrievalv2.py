import requests
import csv
import time
import re
import os
import pandas as pd

# Ensure output directories
OUTPUT_DIR = "output"
INDIVIDUAL_JOURNAL_DIR = os.path.join(OUTPUT_DIR, "individual_journals")
os.makedirs(INDIVIDUAL_JOURNAL_DIR, exist_ok=True)

# SDG Name-to-ID mapping
SDG_NAME_TO_ID = {
    "No Poverty": 1,
    "Zero Hunger": 2,
    "Good Health and Well-Being": 3,
    "Quality Education": 4,
    "Gender Equality": 5,
    "Clean Water and Sanitation": 6,
    "Affordable and Clean Energy": 7,
    "Decent Work and Economic Growth": 8,
    "Industry, Innovation and Infrastructure": 9,
    "Reduced Inequalities": 10,
    "Sustainable Cities and Communities": 11,
    "Responsible Consumption and Production": 12,
    "Climate Action": 13,
    "Life Below Water": 14,
    "Life on Land": 15,
    "Peace, Justice and Strong Institutions": 16,
    "Partnerships for the Goals": 17
}

def reconstruct_abstract(abstract_inverted_index):
    if not abstract_inverted_index:
        return ''
    index = abstract_inverted_index
    try:
        abstract_len = max([max(locs) for locs in index.values()]) + 1
    except ValueError:
        return ''
    abstract = [''] * abstract_len
    for term, positions in index.items():
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
    publisher = "Unknown"  # Default publisher
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

                # Use old logic to fetch SDG IDs and scores
                sdg_ids = []
                if sdgs:
                    sdg_ids = [
                        int(re.findall(r'\d+', sdg.get('id', '').split('/')[-1])[0])
                        for sdg in sdgs
                        if sdg.get('id') and re.findall(r'\d+', sdg.get('id', '').split('/')[-1])
                    ]

                source_id = work.get('primary_location', {}).get('source', {}).get('id')
                if source_id and publisher == "Unknown":
                    publisher = get_publisher_from_source(source_id)
                results.append({
                    'title': title,
                    'abstract': abstract,
                    'sdg_ids': "; ".join(map(str, sdg_ids)),  # Save numeric IDs as string
                    'publisher': publisher
                })
            cursor = data.get('meta', {}).get('next_cursor')
            if not cursor:
                break
            time.sleep(1)  # To avoid rate-limiting
        except Exception as e:
            print(f"Error fetching works for ISSN {issn}: {e}")
            break
    return results

publisher_cache = {}

def get_publisher_from_source(source_id):
    if source_id in publisher_cache:
        return publisher_cache[source_id]
    try:
        source_url = f"https://api.openalex.org/sources/{source_id}"
        time.sleep(1.5)
        response = requests.get(source_url)
        if response.status_code == 200:
            source_data = response.json()
            publisher = source_data.get('parent_publisher', 'Unknown')
            if publisher == 'Unknown':
                publisher = source_data.get('display_name', 'Unknown')
            publisher_cache[source_id] = publisher
            return publisher
        elif response.status_code == 429:
            print(f"Rate limit hit for source ID {source_id}. Retrying after delay...")
            time.sleep(5)
            return get_publisher_from_source(source_id)
        else:
            print(f"Failed to fetch publisher for source ID {source_id}: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error fetching publisher for source ID {source_id}: {e}")
    return "Unknown"

def calculate_sdgi_score(df):
    total_articles = len(df)
    sdg_column = df['sdg_ids'].dropna()

    # Calculate SDG Presence
    articles_with_sdg = sdg_column[sdg_column != ""].count()
    sdg_presence = (articles_with_sdg / total_articles) * 100 if total_articles > 0 else 0

    # Split sdg_ids and explode
    sdg_exploded = sdg_column.str.split("; ").explode()

    # Filter out empty strings
    sdg_exploded = sdg_exploded[sdg_exploded != '']

    # Count SDGs
    sdg_counts = sdg_exploded.value_counts()

    if not sdg_counts.empty:
        top_sdgs = sdg_counts.head(3)
        top_sdg_total = top_sdgs.sum()
        top_sdg_dominance = (top_sdgs.iloc[0] / top_sdg_total) * 100 if top_sdg_total > 0 else 0

        # Extract Top 3 SDGs as numeric IDs, ignoring invalid entries
        top_sdg_ids = []
        for sdg in top_sdgs.index:
            try:
                top_sdg_ids.append(int(sdg))
            except ValueError:
                top_sdg_ids.append("Unknown")
    else:
        top_sdgs = []
        top_sdg_total = 0
        top_sdg_dominance = 0
        top_sdg_ids = ["Unknown", "Unknown", "Unknown"]

    # Ensure Top SDG IDs list has exactly 3 elements
    while len(top_sdg_ids) < 3:
        top_sdg_ids.append("Unknown")

    # SDGII Score
    sdgii_score = (0.5 * sdg_presence) + (0.5 * top_sdg_dominance)
    print(top_sdg_ids)
    return {
        "Total Articles": total_articles,
        "SDG Presence (%)": round(sdg_presence, 2),
        "Top SDG Dominance (%)": round(top_sdg_dominance, 2),
        "SDGII Score (%)": round(sdgii_score, 2),
        "Top SDG 1": top_sdg_ids[0],
        "Top SDG 2": top_sdg_ids[1],
        "Top SDG 3": top_sdg_ids[2]
    }

def save_individual_journal_file(journal_name, data):
    filename = os.path.join(INDIVIDUAL_JOURNAL_DIR, f"{journal_name}_data.csv")
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False)
    print(f"Individual data saved to {filename}")

def process_journal(issn, journal_name, start_year, end_year):
    data = get_works_for_issn(issn, start_year, end_year)
    if not data:
        print(f"No data retrieved for journal '{journal_name}'. Skipping.")
        return None
    save_individual_journal_file(journal_name, data)

    df = pd.DataFrame(data)
    publisher = df['publisher'].iloc[0] if 'publisher' in df.columns and not df['publisher'].empty else 'Unknown'
    sdgi_scores = calculate_sdgi_score(df)
    sdgi_scores.update({
        "Journal": journal_name,
        "ISSN": issn,
        "Publisher": publisher
    })
    return sdgi_scores

def process_all_journals(journals_csv_path, start_year, end_year, output_csv):
    if not os.path.exists(journals_csv_path):
        print(f"Error: '{journals_csv_path}' not found.")
        return

    results = []
    with open(journals_csv_path, mode='r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            issn = row.get('ISSN')
            journal_name = row.get('Journal')
            if issn and journal_name:
                print(f"Processing journal '{journal_name}' with ISSN {issn}")
                result = process_journal(issn, journal_name, start_year, end_year)
                if result:
                    results.append(result)

    if results:
        fieldnames = ["Journal", "ISSN", "Publisher", "Total Articles", "SDG Presence (%)", 
                      "Top SDG Dominance (%)", "SDGII Score (%)", "Top SDG 1", "Top SDG 2", "Top SDG 3"]
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, output_csv)
        with open(output_path, mode='w', encoding='utf-8', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"All journal SDGII scores have been written to '{output_path}'.")

if __name__ == "__main__":
    journals_csv_path = 'alabama.csv'  # Input file path
    start_year = 2020  # Start year for fetching articles
    end_year = 2023 # End year for fetching articles
    output_csv = f'journal_grades_alabama_{start_year}_{end_year}.csv'  # Output file name

    # Call the main processing function
    process_all_journals(journals_csv_path, start_year, end_year, output_csv)
