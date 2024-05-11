import logging
import tenacity
import json
from bs4 import BeautifulSoup
from selenium import webdriver
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials
from os import environ
from time import sleep


class ScriptError(Exception):
    pass


def get_chrome_options():
    """Returns a ChromeOptions object with various options set."""
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
    for key, value in options.items():
        if value:
            chrome_options.add_argument(f"--{key}")
        else:
            chrome_options.add_argument(f"--{key}={value}")
    return chrome_options


@tenacity.retry(wait=tenacity.wait_exponential(), stop=tenacity.stop_after_attempt(3))
def scrape_polla():
    """
    Scrape polla.cl for prize information.
    
    Returns:
    List: List of prizes in Chilean pesos.
    """
    try:
        options = get_chrome_options()
        with webdriver.Chrome(options=options) as driver:
            driver.get("http://www.polla.cl/es")
            driver.find_element("xpath", "//div[3]/div/div/div/img").click()
            text = BeautifulSoup(driver.page_source, "html.parser")
            prizes = text.find_all("span", class_="prize")
            prizes = [int(prize.text.strip("$").replace(".", "")) * 1000000 for prize in prizes]
            if sum(prizes) == 0:
                raise ScriptError("Sum of prizes is still zero after 3 tries. Aborting script.")
            return prizes
    except Exception as error:
        raise ScriptError(f"An error occurred: {error}")


def get_credentials():
    """
    Retrieves Google OAuth2 service account credentials from an environment variable.

    Returns:
    Credentials: An object containing the service account credentials.

    Raises:
    KeyError: If the CREDENTIALS environment variable is not set.
    """
    try:
        credentials_json = json.loads(environ["CREDENTIALS"])
        creds = Credentials.from_service_account_info(credentials_json)
        return creds
    except KeyError:
        raise ScriptError("Error: CREDENTIALS environment variable not set.")
    except Exception as e:
        raise ScriptError(f"Error: {e}")


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
        logging.info(f"{response['updatedCells']} cells updated. Total prizes: {prizes[0]}.")
    except HttpError as error:
        raise HttpError(f"An error occurred: {error}")


if __name__ == "__main__":
    try:
        update_google_sheet()
    except ScriptError as error:
        logging.error(f"Script Error: {error}")
