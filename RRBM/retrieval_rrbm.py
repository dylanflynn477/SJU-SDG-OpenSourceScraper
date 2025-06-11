import os
import time
import pandas as pd
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import chromedriver_autoinstaller
import glob

# Ensure correct ChromeDriver version
chromedriver_autoinstaller.install()

# Load environment variables
load_dotenv()
USERNAME = os.getenv("RRBM_USERNAME")
PASSWORD = os.getenv("RRBM_PASSWORD")

# Google Sheets Configuration
GOOGLE_CREDENTIALS_FILE = 'weighty-archive-449420-v8-1c9c00e21ff3.json'
GOOGLE_SHEET_ID = '1hk7F7xh1RMHFmvJ20FHQiZizyYaJjXV5qsdnVu0Qdeg'
SHEET_NAME = "Sheet4"

# Authenticate with Google Sheets
scopes = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
client = gspread.authorize(creds)
sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_NAME)

# Set up download directory
download_dir = os.path.join(os.getcwd(), "downloads")
os.makedirs(download_dir, exist_ok=True)

# Set up Selenium WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--headless")  
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_experimental_option("prefs", {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "safebrowsing.enabled": True
})

# Initialize WebDriver
driver = webdriver.Chrome(options=options)

def wait_for_csv(directory, timeout=15):
    """Waits for a new CSV file to appear in the directory."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        csv_files = glob.glob(os.path.join(directory, "*.csv"))
        if csv_files:
            return max(csv_files, key=os.path.getctime)  # Most recent CSV
        time.sleep(1)  
    raise TimeoutError("CSV file did not appear in time!")

def login_and_download_csv():
    """Logs into RRBM and downloads the correct CSV file."""
    login_url = "https://rrbm.submissions.network/index.php/RRBM/login"
    reports_url = "https://rrbm.submissions.network/index.php/RRBM/stats/reports"
    download_xpath = "//*[@id=\"app\"]/div[1]/main/div/div/ul/li[1]/a"

    driver.get(login_url)
    time.sleep(3)

    # Enter username and password
    driver.find_element(By.NAME, "username").send_keys(USERNAME)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD + Keys.RETURN)
    time.sleep(5)

    # Navigate to reports page
    driver.get(reports_url)
    time.sleep(3)

    # Click the download link
    driver.find_element(By.XPATH, download_xpath).click()
    time.sleep(5)

    # Wait for the correct CSV file
    downloaded_file_path = wait_for_csv(download_dir)
    return downloaded_file_path

def upload_to_google_sheets(csv_file):
    """Uploads cleaned CSV data to Google Sheets."""
    df = pd.read_csv(csv_file)

    # Replace NaN and infinite values with a placeholder (e.g., empty string)
    df = df.replace([float('inf'), float('-inf')], 0)  # Replace infinity with 0
    df = df.fillna('')  # Replace NaN with an empty string

    # Convert all data to string format (ensures JSON safety)
    df = df.astype(str)

    # Upload to Google Sheets
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("Data uploaded successfully to Google Sheets.")

if __name__ == "__main__":
    csv_filename = login_and_download_csv()
    upload_to_google_sheets(csv_filename)
    driver.quit()
