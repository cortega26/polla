"""
Polla.cl Prize Scraper and Google Sheets Updater (GitHub Actions Optimized)
Maintains all original functionality with CI improvements
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
from selenium.webdriver.chrome.service import Service
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from logging import getLogger, INFO, FileHandler, StreamHandler, Formatter
from os import environ
import traceback
from webdriver_manager.chrome import ChromeDriverManager

# Configure logging
logger = getLogger(__name__)
logger.setLevel(INFO)

formatter = Formatter(
    '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

console_handler = StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

if "GITHUB_ACTIONS" not in environ:
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = FileHandler(log_dir / f"polla_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"File logging disabled: {e}")

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
    base_url: str = "https://www.polla.cl/es"
    timeout: int = 30
    retry_multiplier: int = 1
    min_retry_wait: int = 60
    max_attempts: int = 5
    element_timeout: int = 15
    page_load_timeout: int = 45

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
        return cls()

class ScriptError(Exception):
    """Enhanced error handling for CI"""
    def __init__(self, message: str, original_error: Optional[Exception] = None, error_code: Optional[str] = None):
        self.message = message
        self.original_error = original_error
        self.error_code = error_code
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc() if original_error else None
        super().__init__(self.get_error_message())

    def get_error_message(self) -> str:
        base_msg = f"[{self.error_code}] {self.message}" if self.error_code else self.message
        return f"{base_msg} | Original: {str(self.original_error)}" if self.original_error else base_msg

    def log_error(self):
        logger.error(f"Error @ {self.timestamp.isoformat()}")
        logger.error(f"Message: {self.message}")
        if self.error_code: logger.error(f"Code: {self.error_code}")
        if self.original_error: logger.error(f"Original: {str(self.original_error)}")
        if self.traceback: logger.error(f"Traceback:\n{self.traceback}")

@dataclass(frozen=True)
class PrizeData:
    """Full original data structure"""
    loto: int
    recargado: int
    revancha: int
    desquite: int
    jubilazo: int
    multiplicar: int
    jubilazo_50: int

    def __post_init__(self):
        for field_name, value in self.__dict__.items():
            if value < 0:
                raise ValueError(f"Prize cannot be negative: {field_name}={value}")

    def to_sheet_values(self) -> List[List[int]]:
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
        return sum(self.__dict__.values())

class BrowserManager:
    """CI-optimized browser management"""
    def __init__(self, config: AppConfig):
        self.config = config
        self._driver: Optional[WebDriver] = None

    def _configure_chrome_options(self) -> webdriver.ChromeOptions:
        options = webdriver.ChromeOptions()
        chrome_config = self.config.chrome.__dict__
        
        for key, value in chrome_config.items():
            if key.startswith('_'): continue
            if isinstance(value, bool) and value:
                options.add_argument(f"--{key}")
            elif not isinstance(value, bool):
                options.add_argument(f"--{key}={value}")
        
        options.add_argument('--disable-infobars')
        options.add_argument('--remote-debugging-port=9222')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        return options

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        retry=tenacity.retry_if_exception_type(ScriptError)
    )
    def get_driver(self) -> WebDriver:
        try:
            if not self._driver:
                options = self._configure_chrome_options()
                service = Service(ChromeDriverManager().install())
                self._driver = webdriver.Chrome(service=service, options=options)
                self._driver.set_page_load_timeout(self.config.scraper.page_load_timeout)
            return self._driver
        except Exception as e:
            raise ScriptError("Browser initialization failed", e, "BROWSER_INIT")

    def close(self):
        try:
            if self._driver:
                self._driver.quit()
                self._driver = None
        except Exception as e:
            logger.warning(f"Browser close error: {e}")

class PollaScraper:
    """Full original scraping logic with CI enhancements"""
    def __init__(self, config: AppConfig, browser_manager: BrowserManager):
        self.config = config
        self.browser_manager = browser_manager
        self._driver = None
        self._wait = None

    def _initialize_driver(self):
        self._driver = self.browser_manager.get_driver()
        self._wait = WebDriverWait(self._driver, self.config.scraper.element_timeout)

    def _wait_and_click(self, xpath: str) -> Optional[WebElement]:
        try:
            element = self._wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            self._driver.execute_script("arguments[0].scrollIntoView(true);", element)
            element.click()
            return element
        except Exception as e:
            logger.warning(f"Click failed on {xpath}: {e}")
            return None

    def _parse_prize(self, text: str) -> int:
        try:
            cleaned = text.strip("$").replace(".", "")
            return int(cleaned) * 1000000 if cleaned else 0
        except (ValueError, AttributeError) as e:
            logger.warning(f"Parse error: {text} - {e}")
            return 0

    def _validate_prizes(self, prizes: List[int]):
        if len(prizes) < 9 or all(p == 0 for p in prizes):
            raise ScriptError("Invalid prize data", error_code="PRIZE_VALIDATION")

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=30),
        stop=tenacity.stop_after_attempt(5),
        retry=tenacity.retry_if_exception_type(ScriptError),
        before_sleep=lambda retry_state: logger.warning(f"Retry #{retry_state.attempt_number}...")
    )
    def scrape(self) -> PrizeData:
        try:
            self._initialize_driver()
            logger.info(f"Navigating to {self.config.scraper.base_url}")
            self._driver.get(self.config.scraper.base_url)
            
            self._close_holiday_popup()
            
            if not self._wait_and_click("//div[3]/div/div/div/img"):
                raise ScriptError("Element interaction failed", error_code="ELEMENT_ERROR")
            
            soup = BeautifulSoup(self._driver.page_source, "html.parser")
            prize_elements = soup.find_all("span", class_="prize")
            
            if not prize_elements:
                raise ScriptError("No prizes found", error_code="NO_PRIZES")
            
            prizes = [self._parse_prize(p.text) for p in prize_elements]
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
            raise ScriptError("Scraping failed", error, "SCRAPE_FAIL") from error

    def _close_holiday_popup(self):
        try:
            short_wait = WebDriverWait(self._driver, 8)
            popup_container = short_wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "div.modal.bannerPopup"))
            )
            close_btn = short_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "span.close"))
            )
            close_btn.click()
            short_wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.modal.bannerPopup")))
        except (TimeoutException, NoSuchElementException):
            logger.info("No popup detected")

class GoogleSheetsManager:
    """Full original Sheets integration with retries"""
    def __init__(self, config: AppConfig):
        self.config = config
        self._service = None

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=5),
        retry=tenacity.retry_if_exception_type(HttpError)
    )
    def update_sheet(self, prize_data: PrizeData) -> None:
        try:
            self._initialize_service()
            body = {"values": prize_data.to_sheet_values()}
            
            response = self._service.spreadsheets().values().update(
                spreadsheetId=self.config.google.spreadsheet_id,
                range=self.config.google.range_name,
                valueInputOption="RAW",
                body=body
            ).execute()
            
            logger.info(
                f"Updated {response.get('updatedCells')} cells | Total: {prize_data.total_prize_money}"
            )
        except HttpError as error:
            self._handle_http_error(error)
        except Exception as error:
            raise ScriptError("Update failed", error, "SHEETS_UPDATE")

    def _initialize_service(self):
        if not self._service:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(environ["CREDENTIALS"]),
                scopes=self.config.google.scopes
            )
            self._service = build("sheets", "v4", credentials=creds)

    def _handle_http_error(self, error: HttpError):
        if error.resp.status == 403:
            raise ScriptError("Permission denied", error, "AUTH_ERROR")
        elif error.resp.status == 404:
            raise ScriptError("Spreadsheet not found", error, "NOT_FOUND")
        else:
            raise ScriptError(f"API Error: {error.resp.status}", error, "API_ERROR")

class PollaApp:
    """Main application flow with CI optimizations"""
    def __init__(self):
        self.config = AppConfig.create_default()
        self.browser_manager = BrowserManager(self.config)
        self.sheets_manager = GoogleSheetsManager(self.config)
        self.scraper = PollaScraper(self.config, self.browser_manager)

    async def run(self) -> None:
        start_time = datetime.now()
        logger.info("Script started")
        
        try:
            prize_data = self.scraper.scrape()
            logger.info("Scraping successful")
            
            self.sheets_manager.update_sheet(prize_data)
            logger.info("Sheets updated")
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Completed in {duration:.2f}s")
            
        except ScriptError as error:
            error.log_error()
            raise
        finally:
            self.browser_manager.close()

def main() -> None:
    try:
        app = PollaApp()
        asyncio.run(app.run())
    except Exception as error:
        logger.critical(f"Fatal error: {str(error)}")
        raise

if __name__ == "__main__":
    main()