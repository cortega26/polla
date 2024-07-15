import tenacity
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from logging import getLogger, basicConfig, INFO
from os import environ
from typing import List

# Configure logging
basicConfig(level=INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = getLogger(__name__)

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

@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=30*60),
    stop=tenacity.stop_after_attempt(4),
    retry=tenacity.retry_if_exception_type(ScriptError),
    before_sleep=lambda retry_state: logger.warning(f"Retrying in {retry_state.next_action.sleep} seconds...")
)
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
            try:
                element = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[3]/div/div/div/img"))
                )
                element.click()
            except Exception as e:
                raise ScriptError(f"Failed to click element: {e}")

            soup = BeautifulSoup(driver.page_source, "html.parser")
            prizes = soup.find_all("span", class_="prize")

            if not prizes:
                raise ScriptError("No prize elements found on the page.")

            prize_values = []
            for prize in prizes:
                try:
                    value = int(prize.text.strip("$").replace(".", "")) * 1000000
                    prize_values.append(value)
                except ValueError as e:
                    logger.warning(f"Failed to parse prize value: {prize.text}. Error: {e}")

            if not prize_values:
                raise ScriptError("Failed to parse any prize values.")

            if sum(prize_values) == 0:
                raise ScriptError("Sum of prizes is zero. This may indicate an issue with the data.")

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
        credentials_json = environ.get("CREDENTIALS", "")
        if not credentials_json:
            raise ScriptError("CREDENTIALS environment variable is empty.")
        creds = service_account.Credentials.from_service_account_info(
            credentials_json,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return creds
    except Exception as error:
        raise ScriptError(f"Error retrieving credentials: {error}")

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
            raise ScriptError(f"Insufficient prize data retrieved. Expected at least 9, got {len(prizes)}.")

        values = [
            [prizes[1]], # Loto
            [prizes[2]], # Recargado
            [prizes[3]], # Revancha
            [prizes[4]], # Desquite
            [prizes[5] + prizes[6]], # Jubizabo 1M y 500K 
            [0], # Multiplicar
            [prizes[7] + prizes[8]] # Jubilazo 1M y 500K 50 años
        ]
        body = {"values": values}

        try:
            response = service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                body=body
            ).execute()
            logger.info(f"{response.get('updatedCells', 0)} cells updated. Total prizes: {prizes[0]}.")
        except HttpError as error:
            if error.resp.status == 403:
                raise ScriptError("Permission denied. Check if the service account has write access to the sheet.")
            elif error.resp.status == 404:
                raise ScriptError("Spreadsheet not found. Check if the spreadsheet ID is correct.")
            else:
                raise ScriptError(f"Google Sheets API error: {error}")
    except Exception as error:
        raise ScriptError(f"Error updating Google Sheet: {error}")

def main() -> None:
    """Main function to run the script with comprehensive error handling."""
    try:
        update_google_sheet()
    except ScriptError as error:
        logger.error(f"Script Error: {error}")
    except Exception as error:
        logger.exception(f"Unexpected error: {error}")


if __name__ == "__main__":
    main()
