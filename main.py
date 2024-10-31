import json
import tenacity
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from logging import getLogger, basicConfig, INFO
from os import environ

# Configure logging with timestamp and log level
basicConfig(
    level=INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = getLogger(__name__)

class ScriptError(Exception):
    """Custom exception for script errors with improved context."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.get_error_message())

    def get_error_message(self) -> str:
        """Formats the error message with the original error if present."""
        if self.original_error:
            return f"{self.message} Original error: {str(self.original_error)}"
        return self.message

@dataclass
class PrizeData:
    """Data class to store prize information."""
    loto: int
    recargado: int
    revancha: int
    desquite: int
    jubilazo: int
    multiplicar: int
    jubilazo_50: int

class Config:
    """Configuration class to store constants and settings."""
    BASE_URL = "http://www.polla.cl/es"
    SPREADSHEET_ID = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
    RANGE_NAME = "Sheet1!A1:A7"
    TIMEOUT = 10
    RETRY_MULTIPLIER = 1
    MIN_RETRY_WAIT = 30 * 60
    MAX_ATTEMPTS = 4
    CHROME_OPTIONS = {
        "headless": True,
        "no-sandbox": True,
        "disable-dev-shm-usage": True,
        "lang": "es",
        "disable-extensions": True,
        "incognito": True,
        "disable-blink-features": "AutomationControlled"
    }

def get_chrome_options() -> webdriver.ChromeOptions:
    """
    Configure and return ChromeOptions with security and performance settings.
    
    Returns:
        webdriver.ChromeOptions: Configured Chrome options
    """
    chrome_options = webdriver.ChromeOptions()
    for key, value in Config.CHROME_OPTIONS.items():
        chrome_options.add_argument(f"--{key}={value}" if value is not True else f"--{key}")
    
    # Add additional security headers
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-software-rasterizer')
    
    return chrome_options

def get_credentials() -> Credentials:
    """
    Retrieves Google OAuth2 service account credentials from an environment variable.
    
    Returns:
        Credentials: An object containing the service account credentials.
    
    Raises:
        ScriptError: If the CREDENTIALS environment variable is not set or credentials are invalid.
    """
    try:
        credentials_json = environ.get("CREDENTIALS")
        if not credentials_json:
            raise ScriptError("CREDENTIALS environment variable is empty")
        
        # Add debug logging
        logger.info("Attempting to parse credentials JSON")
        
        # Handle potential string escaping
        credentials_json = credentials_json.replace('\n', '').replace('\r', '')
        if credentials_json.startswith('"') and credentials_json.endswith('"'):
            credentials_json = credentials_json[1:-1]
        
        try:
            credentials_dict = json.loads(credentials_json)
            # Verify required fields are present
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            missing_fields = [field for field in required_fields if field not in credentials_dict]
            if missing_fields:
                raise ScriptError(f"Credentials JSON missing required fields: {', '.join(missing_fields)}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Raw credentials string: {credentials_json[:100]}...") # Log first 100 chars
            raise ScriptError("Invalid JSON in CREDENTIALS environment variable", e)
            
        return service_account.Credentials.from_service_account_info(
            credentials_dict,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
    except Exception as error:
        raise ScriptError("Error retrieving credentials", error)

class PollaScraper:
    """Class to handle web scraping operations for polla.cl."""
    
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self._wait = WebDriverWait(driver, Config.TIMEOUT)

    def _wait_and_click(self, xpath: str) -> Optional[WebElement]:
        """Wait for and click an element, with proper error handling."""
        try:
            element = self._wait.until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            element.click()
            return element
        except Exception as e:
            logger.warning(f"Failed to click element {xpath}: {e}")
            return None

    def _parse_prize(self, text: str) -> int:
        """
        Parse prize value from text.
        
        Args:
            text: Prize text to parse
            
        Returns:
            int: Parsed prize value in pesos
        """
        try:
            return int(text.strip("$").replace(".", "")) * 1000000
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse prize value: {text}. Error: {e}")
            return 0

    def _validate_prizes(self, prizes: List[int]) -> None:
        """
        Validate scraped prize data.
        
        Args:
            prizes: List of prize values to validate
            
        Raises:
            ScriptError: If validation fails
        """
        if not prizes or len(prizes) < 9:
            raise ScriptError(f"Invalid prize data: expected 9+ prizes, got {len(prizes)}")
        if sum(prizes) == 0:
            raise ScriptError("All prizes are zero - possible scraping error")

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=Config.RETRY_MULTIPLIER, min=Config.MIN_RETRY_WAIT),
        stop=tenacity.stop_after_attempt(Config.MAX_ATTEMPTS),
        retry=tenacity.retry_if_exception_type(ScriptError),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying in {retry_state.next_action.sleep} seconds..."
        )
    )
    def scrape(self) -> PrizeData:
        """
        Scrape prize information from polla.cl.
        
        Returns:
            PrizeData: Structured prize information
            
        Raises:
            ScriptError: If scraping fails
        """
        try:
            self.driver.get(Config.BASE_URL)
            self._wait_and_click("//div[3]/div/div/div/img")
            
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            prizes = [
                self._parse_prize(prize.text)
                for prize in soup.find_all("span", class_="prize")
            ]
            
            self._validate_prizes(prizes)
            
            return PrizeData(
                loto=prizes[1],
                recargado=prizes[2],
                revancha=prizes[3],
                desquite=prizes[4],
                jubilazo=prizes[5] + prizes[6],
                multiplicar=0,
                jubilazo_50=prizes[7] + prizes[8]
            )
            
        except Exception as error:
            raise ScriptError("Scraping failed", error)

def update_google_sheet(prize_data: PrizeData) -> None:
    """
    Update Google Sheet with prize information.
    
    Args:
        prize_data: Prize data to update in the sheet
        
    Raises:
        ScriptError: If update fails
    """
    try:
        creds = get_credentials()
        service = build("sheets", "v4", credentials=creds)
        
        values = [
            [prize_data.loto],
            [prize_data.recargado],
            [prize_data.revancha],
            [prize_data.desquite],
            [prize_data.jubilazo],
            [prize_data.multiplicar],
            [prize_data.jubilazo_50]
        ]
        
        body = {"values": values}

        try:
            response = service.spreadsheets().values().update(
                spreadsheetId=Config.SPREADSHEET_ID,
                range=Config.RANGE_NAME,
                valueInputOption="RAW",
                body=body
            ).execute()
            
            logger.info(
                f"Update successful - {response.get('updatedCells', 0)} cells updated. "
                f"Timestamp: {datetime.now().isoformat()}"
            )
            
        except HttpError as error:
            if error.resp.status == 403:
                raise ScriptError("Permission denied - check service account permissions")
            elif error.resp.status == 404:
                raise ScriptError("Spreadsheet not found - check spreadsheet ID")
            else:
                raise ScriptError(f"Google Sheets API error: {error.resp.status}", error)
                
    except Exception as error:
        raise ScriptError("Error updating Google Sheet", error)

def main() -> None:
    """
    Main function to run the script with comprehensive error handling.
    """
    start_time = datetime.now()
    logger.info(f"Script started at {start_time.isoformat()}")
    
    try:
        options = get_chrome_options()
        with webdriver.Chrome(options=options) as driver:
            scraper = PollaScraper(driver)
            prize_data = scraper.scrape()
            update_google_sheet(prize_data)
            
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Script completed successfully in {duration:.2f} seconds")
        
    except ScriptError as error:
        logger.error(f"Script Error: {error}")
    except Exception as error:
        logger.exception(f"Unexpected error: {error}")

if __name__ == "__main__":
    main()
