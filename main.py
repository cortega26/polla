import os

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from googleapiclient.discovery import build
from google.oauth2 import service_account


def scrape_polla():
    """Scrape polla.cl for prize information.

    Returns:
        list: List of prizes in Chilean pesos.
    """
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("lang=es")
    options.add_argument("--disable-extensions")
    options.add_argument("--incognito")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=options)
    driver.get("http://www.polla.cl/es")
    driver.find_element("xpath", "//div[3]/div/div/div/img").click()
    text = BeautifulSoup(driver.page_source, "html.parser")
    prizes = text.find_all("span", class_="prize")
    driver.close()
    return [int(prize.text.strip("$").replace(".", "")) * 1000000 for prize in prizes]


def update_google_sheet():
    """Update a Google Sheet with the latest prize information from polla.cl."""
    credentials_json = os.environ["CREDENTIALS"]
    with open("service-account.json", "w") as f:
        f.write(credentials_json)
    creds = service_account.Credentials.from_service_account_file("service-account.json")
    service = build("sheets", "v4", credentials=creds)
    spreadsheet_id = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
    range_name = "Sheet1!A1:A7"
    prizes = scrape_polla()
    values = [
        [prizes[1]],
        [prizes[2]],
        [prizes[3]],
        [prizes[4]],
        [prizes[5] + prizes[6]],
        [0],
        [prizes[7] + prizes[8]]
    ]
    body = {"values": values}
    response = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body=body
    ).execute()
    print(f"{response['updatedCells']} cells updated.")
                             

update_google_sheet()

