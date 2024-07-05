import logging
import tenacity
import json
from bs4 import BeautifulSoup
from selenium import webdriver
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials
from os import environ
from typing import List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ScriptError(Exception):
    """Custom exception for script errors"""

def get_chrome_options() -> webdriver.ChromeOptions:
    """Returns a ChromeOptions object with various options set."""
    options_dict = {
        "headless": True,
        "no-sandbox": True,
        "disable-dev-shm-usage": True,
        "lang": "es",
        "disable-extensions": True,
        "incognito": True,
        "disable-blink-features": "AutomationControlled"
    }
    chrome_options = webdriver.ChromeOptions()
    for key, value in options_dict.items():
        chrome_options.add_argument(f"--{key}={value}" if value is not True else f"--{key}")
    return chrome_options

@tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=30*60), stop=tenacity.stop_after_attempt(4))
def scrape_polla() -> List[int]:
    """
    Scrape polla.cl for prize information.
    
    Returns:
    List: List of prizes in Chilean pesos.

    Raises:
    ScriptError: If an error occurs during scraping or if the sum of prizes is zero.
    """
    try:
        options = get_chrome_options()
        with webdriver.Chrome(options=options) as driver:
            driver.get("http://www.polla.cl/es")
            driver.find_element("xpath", "//div[3]/div/div/div/img").click()
            soup = BeautifulSoup(driver.page_source, "html.parser")
            prizes = soup.find_all("span", class_="prize")
            prize_values = [int(prize.text.strip("$").replace(".", "")) * 1000000 for prize in prizes]
            if sum(prize_values) == 0:
                raise ScriptError("Sum of prizes is zero after 3 tries. Aborting script.")
            return prize_values
    except Exception as error:
        raise ScriptError(f"Error occurred while scraping: {error}")

def get_credentials() -> Credentials:
    """
    Retrieves Google OAuth2 service account credentials from an environment variable.

    Returns:
    Credentials: An object containing the service account credentials.

    Raises:
    ScriptError: If the CREDENTIALS environment variable is not set or credentials are invalid.
    """
    try:
        credentials_json = json.loads(environ["CREDENTIALS"])
        creds = Credentials.from_service_account_info(credentials_json)
        return creds
    except KeyError:
        raise ScriptError("CREDENTIALS environment variable not set.")
    except json.JSONDecodeError:
        raise ScriptError("Invalid JSON in CREDENTIALS environment variable.")
    except Exception as e:
        raise ScriptError(f"Error retrieving credentials: {e}")

def update_google_sheet() -> None:
    """
    Update a Google Sheet with the latest prize information from polla.cl.

    Raises:
    ScriptError: If an error occurs during the update process.
    """
    try:
        creds = get_credentials()
        service = build("sheets", "v4", credentials=creds)
        spreadsheet_id = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
        range_name = "Sheet1!A1:A7"
        prizes = scrape_polla()

        if len(prizes) < 9:
            raise ScriptError("Insufficient prize data retrieved.")

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
        raise ScriptError(f"Google Sheets API error: {error}")
    except Exception as error:
        raise ScriptError(f"Error updating Google Sheet: {error}")


if __name__ == "__main__":
    try:
        update_google_sheet()
    except ScriptError as error:
        logging.error(f"Script Error: {error}")
    except Exception as error:
        logging.error(f"Unexpected error: {error}")