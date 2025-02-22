import pandas as pd
import os
import csv
import re
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Directory setup
OUTPUT_DIR = "output"
INDIVIDUAL_JOURNAL_DIR = os.path.join(OUTPUT_DIR, "individual_journals")
os.makedirs(INDIVIDUAL_JOURNAL_DIR, exist_ok=True)

def extract_issn_from_column(df):
    # Clean column names
    df.columns = df.columns.str.strip().str.lower()

    # Extract the ISSN from the 'issn' column
    if "issn" in df.columns:
        issn_column = df["issn"].dropna()
        return issn_column.iloc[0] if not issn_column.empty else ""
    else:
        logging.warning("ISSN column not found.")
    return ""

def calculate_sdgi_score(df):
    total_articles = len(df)
    if 'sustainable development goals' in df.columns:
        sdg_column = df['sustainable development goals'].dropna()
    else:
        sdg_column = pd.Series(dtype=str)
        logging.warning("SDG column not found.")
        return {}

    # Calculate SDG Presence
    articles_with_sdg = sdg_column[sdg_column != ""].count()
    sdg_presence = (articles_with_sdg / total_articles) * 100 if total_articles > 0 else 0

    # Split sdg_ids and explode
    sdg_exploded = sdg_column.str.split('[;,]').explode()

    # Clean and extract SDG numbers
    sdg_exploded = sdg_exploded.str.extract('(\d+)').dropna()
    sdg_exploded = sdg_exploded[sdg_exploded[0].astype(int).between(1, 17)][0].astype(int)

    # Count SDGs
    sdg_counts = sdg_exploded.value_counts()

    if sdg_counts.empty:
        logging.warning("No valid SDG data found.")
        return {}

    top_sdgs = sdg_counts.head(3)
    top_sdg_total = top_sdgs.sum()
    top_sdg_dominance = (top_sdgs.iloc[0] / top_sdg_total) * 100 if top_sdg_total > 0 else 0

    # Extract Top 3 SDGs as numbers
    top_sdg_ids = top_sdgs.index.tolist()

    # Fill missing Top SDGs with blanks
    while len(top_sdg_ids) < 3:
        top_sdg_ids.append("")

    # SDGII Score
    sdgii_score = (0.5 * sdg_presence) + (0.5 * top_sdg_dominance)

    return {
        "File Name": "",  # Placeholder, will be updated later
        "ISSN": "",       # Placeholder, will be updated later
        "Total Articles": total_articles,
        "SDG Presence (%)": round(sdg_presence, 2),
        "Top SDG Dominance (%)": round(top_sdg_dominance, 2),
        "SDGII Score (%)": round(sdgii_score, 2),
        "Top SDG 1": str(top_sdg_ids[0]),
        "Top SDG 2": str(top_sdg_ids[1]),
        "Top SDG 3": str(top_sdg_ids[2]),
    }

def save_individual_data(file_name, df):
    output_file = os.path.join(INDIVIDUAL_JOURNAL_DIR, f"{file_name}_data.csv")
    df.to_csv(output_file, index=False)
    logging.info(f"Saved individual data to {output_file}")

def process_excel_file(file_path):
    results = []
    with pd.ExcelFile(file_path) as xls:
        for sheet_name in xls.sheet_names:
            try:
                # Adjust skiprows based on your file's structure
                df = pd.read_excel(xls, sheet_name=sheet_name, skiprows=1)  # Adjust as needed

                # Clean column names
                df.columns = df.columns.str.strip().str.lower()

                # Print column names for debugging
                logging.info(f"Columns in {file_path}, sheet {sheet_name}: {df.columns.tolist()}")

                if "sustainable development goals" in df.columns:
                    issn = extract_issn_from_column(df)
                    sdgi_scores = calculate_sdgi_score(df)
                    if sdgi_scores:
                        sdgi_scores.update({
                            "File Name": os.path.basename(file_path),
                            "ISSN": issn
                        })
                        results.append(sdgi_scores)
                        save_individual_data(os.path.basename(file_path), df)
                else:
                    logging.warning(f"'Sustainable Development Goals' column not found in {file_path}")
            except Exception as e:
                logging.error(f"Error processing sheet {sheet_name} in {file_path}: {e}")
    return results

def process_all_files_in_folder(folder_path, output_csv):
    summary_results = []
    for file_name in os.listdir(folder_path):
        if file_name.endswith(".xlsx"):
            file_path = os.path.join(folder_path, file_name)
            logging.info(f"Processing file: {file_name}")
            file_results = process_excel_file(file_path)
            if file_results:
                summary_results.extend(file_results)
            else:
                logging.warning(f"No data processed for {file_name}")

    if summary_results:
        fieldnames = [
            "File Name", "ISSN", "Total Articles", "SDG Presence (%)",
            "Top SDG Dominance (%)", "SDGII Score (%)", "Top SDG 1", "Top SDG 2", "Top SDG 3"
        ]
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_file = os.path.join(OUTPUT_DIR, output_csv)
        with open(output_file, mode="w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_results)
        logging.info(f"Summary written to {output_file}.")
        return output_file
    else:
        logging.warning("No summary results to write.")

if __name__ == "__main__":
    folder_path = "2016"  # Replace with your folder containing Excel files
    output_csv = "dimensions_2016.csv"

    # Process all files in the folder
    process_all_files_in_folder(folder_path, output_csv)
