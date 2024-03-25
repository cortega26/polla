import os
import time
import logging
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
RANGE_NAME = "Sheet1!A1:A7"
SERVICE_ACCOUNT_FILE = "service-account.json"
LOG_FILE = "app.log"

# Configure logging
logging.basicConfig(filename=LOG_FILE, level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')


def get_chrome_options():
    """Returns ChromeOptions object with various options set."""
    options = {
        "headless": True,
        "no-sandbox": True,
        "disable-dev-shm-usage": True,
        "lang": "es",
        "disable-extensions": True,
        "incognito": True,
        "disable-blink-features": "AutomationControlled"
    }
    chrome_options = webdriver.chrome.options.Options()
    [chrome_options.add_argument(f"--{key}={value}") for key, value in options.items()]
    return chrome_options


def scrape_polla(driver):
    """
    Scrape polla.cl for prize information.

    Args:
    driver: WebDriver instance.

    Returns:
    List: List of prizes in Chilean pesos.
    """
    try:
        driver.get("http://www.polla.cl/es")
        driver.find_element("xpath", "//div[3]/div/div/div/img").click()
        text = BeautifulSoup(driver.page_source, "html.parser")
        prizes = text.find_all("span", class_="prize")
        prizes = [int(prize.text.strip("$").replace(".", "")) * 1000000 for prize in prizes]
        if sum(prizes) == 0:
            for _ in range(3):
                time.sleep(3600)
                prizes = scrape_polla(driver)
                if sum(prizes) > 0:
                    break
            else:
                raise ValueError("Sum of prizes is still zero after 3 tries.")
        return prizes
    except (WebDriverException, ValueError) as error:
        logging.error(f"An error occurred while scraping polla.cl: {error}")
        raise


def get_credentials():
    """
    Retrieves Google OAuth2 service account credentials from an environment variable.

    Returns:
    Credentials: An object containing the service account credentials.

    Raises:
    KeyError: If the CREDENTIALS environment variable is not set.
    """
    try:
        credentials_json = os.environ["CREDENTIALS"]
        creds = Credentials.from_service_account_info(credentials_json)
        return creds
    except KeyError:
        logging.error("Error: CREDENTIALS environment variable not set.")
        raise


def update_google_sheet():
    """Update a Google Sheet with the latest prize information from polla.cl."""
    try:
        options = get_chrome_options()
        driver = webdriver.Chrome(options=options)
        prizes = scrape_polla(driver)
        creds = get_credentials()
        service = build("sheets", "v4", credentials=creds)
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
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption="RAW",
            body=body
        ).execute()
        print(f"{response['updatedCells']} cells updated. Total prizes: {prizes[0]}.")
    except (HttpError, WebDriverException, ValueError) as error:
        logging.error(f"An error occurred while updating Google Sheet: {error}")
        raise
    finally:
        try:
            driver.quit()
        except NameError:
            pass  # driver variable might not be defined if initialization fails


if __name__ == "__main__":
    update_google_sheet()
