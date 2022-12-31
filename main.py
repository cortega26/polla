from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from os import environ
from sys import exit
from time import sleep


def get_chrome_options():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("lang=es")
    options.add_argument("--disable-extensions")
    options.add_argument("--incognito")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return options


def scrape_polla():
    """Scrape polla.cl for prize information.
    Returns:
        list: List of prizes in Chilean pesos.
    """
    try:
        options = get_chrome_options()
        driver = webdriver.Chrome(options=options)
        driver.get("http://www.polla.cl/es")
        driver.find_element("xpath", "//div[3]/div/div/div/img").click()
        text = BeautifulSoup(driver.page_source, "html.parser")
        prizes = text.find_all("span", class_="prize")
        driver.close()
        prizes = [int(prize.text.strip("$").replace(".", "")) * 1000000 for prize in prizes]
        if sum(prizes) == 0: # Everytime the website is updated, prizes show 0 zero for about 2 hours
            for i in range(3):
                sleep(60 * 60)
                prizes = scrape_polla()
                if sum(prizes) > 0:
                    break
            else:
                print("Sum of prizes is still zero after 3 tries. Aborting script.")
                exit()
        return prizes
    except Exception as e:
        print(f"An error occurred: {e}")
        return []


def get_credentials():
    try:
        credentials_json = environ["CREDENTIALS"]
        with open("service-account.json", "w") as f:
            f.write(credentials_json)
        creds = service_account.Credentials.from_service_account_file("service-account.json")
        return creds
    except KeyError:
        print("Error: CREDENTIALS environment variable not set.")
        
        
def update_google_sheet():
    """Update a Google Sheet with the latest prize information from polla.cl."""
    try:
        creds = get_credentials()
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
        print(f"{response['updatedCells']} cells updated. Total prizes: {prizes[0]}.")
    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    update_google_sheet()
