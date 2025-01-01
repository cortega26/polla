"""
Polla.cl Prize Scraper and Google Sheets Updater
Scrapes lottery prize information and updates a Google Sheet with the results.
"""

import json
import tenacity
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import asyncio
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from logging import getLogger, INFO, FileHandler, StreamHandler, Formatter
from os import environ
import traceback

# Create logger
logger = getLogger(__name__)
logger.setLevel(INFO)

# Create formatter
formatter = Formatter(
    '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create and configure console handler first (this will always work)
console_handler = StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Try to set up file logging, but don't fail if it's not possible
try:
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"polla_{datetime.now().strftime('%Y%m%d')}.log"

    # Create and configure file handler
    file_handler = FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    logger.warning(f"Could not set up file logging: {e}")

# Prevent logging from propagating to the root logger
logger.propagate = False

@dataclass(frozen=True)
class ChromeConfig:
    """Chrome browser configuration settings."""
    headless: bool = True
    no_sandbox: bool = True
    disable_dev_shm_usage: bool = True
    lang: str = "es"
    disable_extensions: bool = True
    incognito: bool = True
    disable_blink_features: str = "AutomationControlled"
    disable_gpu: bool = True
    disable_software_rasterizer: bool = True
    window_size: str = "1920,1080"
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

@dataclass(frozen=True)
class ScraperConfig:
    """Scraper configuration settings."""
    base_url: str = "http://www.polla.cl/es"
    timeout: int = 10
    retry_multiplier: int = 1
    min_retry_wait: int = 60
    max_attempts: int = 4
    element_timeout: int = 5
    page_load_timeout: int = 30

@dataclass(frozen=True)
class GoogleConfig:
    """Google Sheets configuration settings."""
    spreadsheet_id: str = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
    range_name: str = "Sheet1!A1:A7"
    scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/spreadsheets",)
    retry_attempts: int = 3
    retry_delay: int = 5

@dataclass(frozen=True)
class AppConfig:
    """Application configuration container."""
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    
    @classmethod
    def create_default(cls) -> 'AppConfig':
        """Creates a default configuration instance."""
        return cls()

    def get_chrome_options(self) -> Dict[str, Any]:
        """Returns Chrome options as a dictionary."""
        return {
            k: v for k, v in self.chrome.__dict__.items()
            if not k.startswith('_')
        }

class ScriptError(Exception):
    """
    Custom exception for script errors with improved context and tracking.
    Allows for consistent handling and logging of errors throughout the script.
    """
    
    def __init__(
        self, 
        message: str, 
        original_error: Optional[Exception] = None,
        error_code: Optional[str] = None
    ):
        self.message = message
        self.original_error = original_error
        self.error_code = error_code
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc() if original_error else None
        super().__init__(self.get_error_message())

    def get_error_message(self) -> str:
        """Formats the error message with context."""
        base_msg = f"[{self.error_code}] {self.message}" if self.error_code else self.message
        if self.original_error:
            return f"{base_msg} Original error: {str(self.original_error)}"
        return base_msg

    def log_error(self, logger):
        """Logs the error with full context."""
        logger.error(f"Error occurred at {self.timestamp.isoformat()}")
        logger.error(f"Message: {self.message}")
        if self.error_code:
            logger.error(f"Error code: {self.error_code}")
        if self.original_error:
            logger.error(f"Original error: {str(self.original_error)}")
        if self.traceback:
            logger.error(f"Traceback:\n{self.traceback}")

@dataclass(frozen=True)
class PrizeData:
    """Immutable data class to store prize information."""
    loto: int
    recargado: int
    revancha: int
    desquite: int
    jubilazo: int
    multiplicar: int
    jubilazo_50: int

    def __post_init__(self):
        """Validates prize data after initialization."""
        for field_name, value in self.__dict__.items():
            if value < 0:
                raise ValueError(f"Prize amount cannot be negative: {field_name}={value}")

    def to_sheet_values(self) -> List[List[int]]:
        """
        Converts prize data to a 2D list format required by Google Sheets.
        Each sublist represents a row in the target sheet range.
        """
        return [
            [self.loto],
            [self.recargado],
            [self.revancha],
            [self.desquite],
            [self.jubilazo],
            [self.multiplicar],
            [self.jubilazo_50]
        ]

    @property
    def total_prize_money(self) -> int:
        """Calculates total prize money across all categories."""
        return sum([
            self.loto, self.recargado, self.revancha, 
            self.desquite, self.jubilazo, self.multiplicar, 
            self.jubilazo_50
        ])

class BrowserManager:
    """Manages browser instance and configuration."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self._driver: Optional[WebDriver] = None

    def _configure_chrome_options(self) -> webdriver.ChromeOptions:
        """
        Configures Chrome options with security and performance settings.
        
        Returns:
            webdriver.ChromeOptions: Configured Chrome options
        """
        chrome_options = webdriver.ChromeOptions()
        
        # Add core options
        for key, value in self.config.get_chrome_options().items():
            if isinstance(value, bool):
                if value:
                    chrome_options.add_argument(f"--{key}")
            else:
                chrome_options.add_argument(f"--{key}={value}")
        
        # Add security and performance options
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        return chrome_options

    def get_driver(self) -> WebDriver:
        """
        Creates and configures a new WebDriver instance if not already created.
        
        Returns:
            WebDriver: Configured Chrome WebDriver instance
        
        Raises:
            ScriptError: If driver creation fails
        """
        try:
            if not self._driver:
                options = self._configure_chrome_options()
                self._driver = webdriver.Chrome(options=options)
                self._driver.set_page_load_timeout(self.config.scraper.page_load_timeout)
            return self._driver
        except Exception as e:
            raise ScriptError("Failed to create browser instance", e, "BROWSER_INIT_ERROR")

    def close(self):
        """Safely closes the browser instance."""
        try:
            if self._driver:
                self._driver.quit()
                self._driver = None
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")

class PollaScraper:
    """
    Class to handle web scraping operations for polla.cl.
    Assumes the site returns at least 9 'prize' elements in a specific order.
    Index usage in `scrape()` is based on that assumption.
    """
    
    def __init__(self, config: AppConfig, browser_manager: BrowserManager):
        self.config = config
        self.browser_manager = browser_manager
        self._driver = None
        self._wait = None

    def _initialize_driver(self):
        """Initializes WebDriver and WebDriverWait instances."""
        self._driver = self.browser_manager.get_driver()
        self._wait = WebDriverWait(
            self._driver, 
            self.config.scraper.element_timeout
        )

    def _wait_and_click(self, xpath: str) -> Optional[WebElement]:
        """
        Waits for an element to be clickable and clicks it.
        
        Args:
            xpath (str): XPath selector for the element
            
        Returns:
            WebElement if clicked successfully, None otherwise
            
        Raises:
            TimeoutException: If element is not clickable within timeout
        """
        try:
            element = self._wait.until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            # Add a small delay for stability
            self._driver.execute_script("arguments[0].scrollIntoView(true);", element)
            element.click()
            return element
        except Exception as e:
            logger.warning(f"Failed to click element {xpath}: {e}")
            return None

    def _parse_prize(self, text: str) -> int:
        """
        Parses prize text as a value in millions of pesos.
        
        For example, if the text is '$900', we interpret that as 900 (millions).
        This function removes any '$' and '.' characters, converts to int,
        and multiplies by 1,000,000 to get the final peso value.
        
        Returns:
            int: Parsed prize value in pesos, or 0 if parsing fails.
        """
        try:
            cleaned_text = text.strip("$").replace(".", "")
            if not cleaned_text:
                raise ValueError("Empty prize value")
            return int(cleaned_text) * 1000000
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse prize value: {text}. Error: {e}")
            return 0

    def _validate_prizes(self, prizes: List[int]) -> None:
        """
        Validates scraped prize data.
        
        Ensures there are enough prizes and that not all are zero.
        
        Args:
            prizes (List[int]): List of prize values to validate
            
        Raises:
            ScriptError: If validation fails
        """
        if not prizes:
            raise ScriptError(
                "No prizes found", 
                error_code="NO_PRIZES_ERROR"
            )
        if len(prizes) < 9:
            raise ScriptError(
                f"Invalid prize data: expected 9+ prizes, got {len(prizes)}", 
                error_code="INSUFFICIENT_PRIZES_ERROR"
            )
        if all(prize == 0 for prize in prizes):
            raise ScriptError(
                "All prizes are zero - possible scraping error",
                error_code="ZERO_PRIZES_ERROR"
            )

    @tenacity.retry(
        wait=tenacity.wait_exponential(
            multiplier=ScraperConfig.retry_multiplier,
            min=ScraperConfig.min_retry_wait
        ),
        stop=tenacity.stop_after_attempt(ScraperConfig.max_attempts),
        retry=tenacity.retry_if_exception_type(ScriptError),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying in {retry_state.next_action.sleep} seconds..."
        ),
        after=lambda retry_state: logger.info(
            f"Attempt {retry_state.attempt_number} "
            f"{'successful' if not retry_state.outcome.failed else 'failed'}"
        )
    )
    def scrape(self) -> PrizeData:
        """
        Scrapes prize information from polla.cl and maps them to PrizeData.
        
        We assume the page provides at least 9 span.prize elements.
        The second through ninth elements correspond to:
          [1]->Loto, [2]->Recargado, [3]->Revancha, [4]->Desquite,
          [5] and [6] combined -> Jubilazo, [7] and [8] combined -> Jubilazo_50,
        ignoring [0] for site-specific reasons.
        
        Returns:
            PrizeData: Structured prize information
        
        Raises:
            ScriptError: If scraping fails
        """
        try:
            self._initialize_driver()
            
            # Load the page
            logger.info(f"Accessing URL: {self.config.scraper.base_url}")
            self._driver.get(self.config.scraper.base_url)

            # Attempt to close the holiday popup if it appears
            self._close_holiday_popup()
            
            # Click necessary elements
            # XPATH might need to be updated if the site changes structure
            if not self._wait_and_click("//div[3]/div/div/div/img"):
                raise ScriptError(
                    "Failed to interact with required elements",
                    error_code="ELEMENT_INTERACTION_ERROR"
                )
            
            # Parse the page
            soup = BeautifulSoup(self._driver.page_source, "html.parser")
            prize_elements = soup.find_all("span", class_="prize")
            
            if not prize_elements:
                raise ScriptError(
                    "No prize elements found on page",
                    error_code="NO_ELEMENTS_ERROR"
                )
            
            # Extract prizes (ignoring the 0th element per site structure)
            prizes = [self._parse_prize(prize.text) for prize in prize_elements]
            self._validate_prizes(prizes)
            
            # Create PrizeData object
            # Note: We skip prizes[0], as that's the total of all prizes and it's not used
            # based on the current site. If the site changes, this indexing may need to be updated.
            return PrizeData(
                loto=prizes[1],
                recargado=prizes[2],
                revancha=prizes[3],
                desquite=prizes[4],
                jubilazo=prizes[5] + prizes[6],
                multiplicar=0,
                jubilazo_50=prizes[7] + prizes[8]
            )
        except ScriptError:
            raise
        except Exception as error:
            raise ScriptError(
                "Scraping failed",
                error,
                "SCRAPE_ERROR"
            )
        finally:
            # Don't close the browser here as it's managed by BrowserManager
            pass

    def _close_holiday_popup(self):
        """
        Attempts to close the holiday popup if it is present.
        """
        try:
            short_wait = WebDriverWait(self._driver, 8)

            # 1) Wait up to 8s for the modal container (popup) to be visible
            popup_container = short_wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "div.modal.bannerPopup"))
            )
            logger.info("Popup container is visible, proceeding to close it...")

            # 2) Wait specifically for the close <span> to be clickable
            close_btn = short_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "span.close"))
            )
            
            # 3) Normal click; use JS click if the normal click fails
            close_btn.click()
            
            # 4) Wait for the bannerPopup to vanish from the DOM or become invisible
            short_wait.until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.modal.bannerPopup"))
            )
            logger.info("Popup is now closed or invisible.")
            
        except (TimeoutException, NoSuchElementException):
            logger.info("No holiday popup found (or not clickable). Proceeding anyway.")

class CredentialManager:
    """Manages Google API credentials."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        
    @staticmethod
    def _validate_credentials_dict(creds_dict: Dict[str, Any]) -> None:
        """
        Validates the credential dictionary has required fields.
        
        Args:
            creds_dict: Dictionary containing credentials
            
        Raises:
            ScriptError: If required fields are missing
        """
        required_fields = [
            'type', 'project_id', 'private_key_id', 
            'private_key', 'client_email'
        ]
        
        missing_fields = [
            field for field in required_fields 
            if field not in creds_dict
        ]
        
        if missing_fields:
            raise ScriptError(
                f"Missing required credential fields: {', '.join(missing_fields)}",
                error_code="INVALID_CREDENTIALS"
            )

    def get_credentials(self) -> Credentials:
        """
        Retrieves and validates Google OAuth2 service account credentials.
        
        Returns:
            Credentials: Valid Google service account credentials
            
        Raises:
            ScriptError: If credentials are invalid or missing
        """
        try:
            # Log available environment variables (excluding sensitive ones)
            sensitive_terms = {'key', 'secret', 'password', 'token', 'credential'}
            env_vars = [
                k for k in environ.keys() 
                if not any(term in k.lower() for term in sensitive_terms)
            ]
            logger.info("Available environment variables: %s", ", ".join(sorted(env_vars)))
            
            # Get credentials from environment
            credentials_json = environ.get("CREDENTIALS")
            
            if not credentials_json:
                logger.error("CREDENTIALS environment variable is not set")
                logger.info("Please ensure the GOOGLE_CREDENTIALS secret is properly set in GitHub Actions")
                raise ScriptError(
                    "CREDENTIALS environment variable is empty",
                    error_code="MISSING_CREDENTIALS"
                )
            
            logger.info("Credentials variable found with length: %d", len(credentials_json))
            
            try:
                credentials_dict = json.loads(credentials_json)
                logger.info("Successfully parsed credentials JSON")
                
                # Validate credentials
                self._validate_credentials_dict(credentials_dict)
                logger.info("All required credential fields present")
                
                return service_account.Credentials.from_service_account_info(
                    credentials_dict,
                    scopes=self.config.google.scopes
                )
                
            except json.JSONDecodeError as e:
                logger.error("Failed to parse credentials JSON: %s", str(e))
                # Log the first few characters of the credentials for debugging
                if credentials_json:
                    preview = credentials_json[:10] + "..." if len(credentials_json) > 10 else "EMPTY"
                    logger.error("First few characters of credentials: %s", preview)
                raise ScriptError(
                    "Invalid JSON in CREDENTIALS environment variable",
                    e,
                    "INVALID_JSON"
                )
                
        except Exception as error:
            if isinstance(error, ScriptError):
                raise  # Re-raise ScriptError without wrapping
            raise ScriptError(
                "Error retrieving credentials",
                error,
                "CREDENTIAL_ERROR"
            )

class GoogleSheetsManager:
    """Manages Google Sheets operations."""
    
    def __init__(self, config: AppConfig, credential_manager: CredentialManager):
        self.config = config
        self.credential_manager = credential_manager
        self._service = None

    def _initialize_service(self):
        """Initializes the Google Sheets service if it is not already initialized."""
        if not self._service:
            creds = self.credential_manager.get_credentials()
            self._service = build("sheets", "v4", credentials=creds)

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=5),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type((HttpError, ScriptError))
    )
    def update_sheet(self, prize_data: PrizeData) -> None:
        """
        Updates Google Sheet with prize information.
        
        Args:
            prize_data (PrizeData): Prize data to update in the sheet
            
        Raises:
            ScriptError: If update fails
        """
        try:
            self._initialize_service()
            
            values = prize_data.to_sheet_values()
            body = {"values": values}

            try:
                response = self._service.spreadsheets().values().update(
                    spreadsheetId=self.config.google.spreadsheet_id,
                    range=self.config.google.range_name,
                    valueInputOption="RAW",
                    body=body
                ).execute()
                
                logger.info(
                    "Update successful - %d cells updated. "
                    "Total prizes: %d. Timestamp: %s",
                    response.get('updatedCells', 0),
                    prize_data.total_prize_money,
                    datetime.now().isoformat()
                )
                
            except HttpError as error:
                if error.resp.status == 403:
                    raise ScriptError(
                        "Permission denied - check service account permissions",
                        error,
                        "PERMISSION_DENIED"
                    )
                elif error.resp.status == 404:
                    raise ScriptError(
                        "Spreadsheet not found - check spreadsheet ID",
                        error,
                        "SPREADSHEET_NOT_FOUND"
                    )
                else:
                    raise ScriptError(
                        f"Google Sheets API error: {error.resp.status}",
                        error,
                        "SHEETS_API_ERROR"
                    )
                    
        except Exception as error:
            raise ScriptError(
                "Error updating Google Sheet",
                error,
                "UPDATE_ERROR"
            )

class PollaApp:
    """Main application class orchestrating the scraping and updating process."""
    
    def __init__(self):
        self.config = AppConfig.create_default()
        self.browser_manager = BrowserManager(self.config)
        self.credential_manager = CredentialManager(self.config)
        self.sheets_manager = GoogleSheetsManager(
            self.config,
            self.credential_manager
        )
        self.scraper = PollaScraper(
            self.config,
            self.browser_manager
        )

    async def run(self) -> None:
        """
        Main execution flow with proper resource management.
        
        1. Scrapes the prize data from the website.
        2. Updates the Google Sheet with the scraped values.
        3. Logs execution details.
        """
        start_time = datetime.now()
        logger.info("Script started at %s", start_time.isoformat())
        
        try:
            # Scrape prizes
            prize_data = self.scraper.scrape()
            logger.info("Successfully scraped prize data")
            
            # Update Google Sheet
            self.sheets_manager.update_sheet(prize_data)
            logger.info("Successfully updated Google Sheet")
            
            # Calculate and log execution time
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info("Script completed successfully in %.2f seconds", duration)
            
        except ScriptError as error:
            error.log_error(logger)
        except Exception as error:
            logger.exception("Unexpected error occurred")
            raise
        finally:
            self.browser_manager.close()

def main() -> None:
    """
    Entry point with asyncio support.
    Initializes PollaApp and runs the asynchronous flow.
    """
    try:
        app = PollaApp()
        asyncio.run(app.run())
    except Exception as error:
        logger.critical("Fatal error occurred: %s", str(error))
        raise

if __name__ == "__main__":
    main()
