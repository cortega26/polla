"""
Polla.cl Prize Scraper & Google Sheets Updater
Robust version combining original working logic with essential optimizations
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from selenium import webdriver
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# --------------------------
# Configuration
# --------------------------
@dataclass(frozen=True)
class AppConfig:
    chrome_version: str = "116.0.5845.96"
    headless: bool = True
    base_url: str = "https://www.polla.cl/es"
    spreadsheet_id: str = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
    sheets_range: str = "Sheet1!A1:A7"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5

    @classmethod
    def from_env(cls):
        return cls(
            headless=os.getenv("HEADLESS", "true").lower() == "true",
            chrome_version=os.getenv("CHROME_VERSION", "116.0.5845.96")
        )

# --------------------------
# Logging Setup
# --------------------------
def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (only in non-CI environments)
    if not os.getenv("CI"):
        try:
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            file_handler = logging.FileHandler(log_dir / f"polla_{datetime.now().strftime('%Y%m%d')}.log")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning("Could not setup file logging: %s", e)

    return logger

logger = setup_logging()

# --------------------------
# Core Functionality
# --------------------------
class BrowserManager:
    """Manages Chrome browser instance with version control"""
    def __init__(self, config: AppConfig):
        self.config = config
        self.driver = None

    def __enter__(self):
        self.driver = self.create_driver()
        return self.driver

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            try:
                self.driver.quit()
            except WebDriverException as e:
                logger.warning("Error closing browser: %s", e)

    def create_driver(self) -> WebDriver:
        """Create Chrome driver with version-controlled setup"""
        options = webdriver.ChromeOptions()
        if self.config.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

        service = Service(
            ChromeDriverManager(version=self.config.chrome_version).install()
        )
        
        return webdriver.Chrome(
            service=service,
            options=options
        )

class PrizeScraper:
    """Main scraping logic with essential improvements"""
    def __init__(self, config: AppConfig):
        self.config = config
        self.retries = 0

    def scrape_prizes(self) -> Dict[str, int]:
        """Main scraping workflow with retry logic"""
        while self.retries < self.config.max_retries:
            try:
                with BrowserManager(self.config) as driver:
                    return self._perform_scraping(driver)
            except Exception as e:
                self.retries += 1
                logger.warning("Scraping attempt %d failed: %s", self.retries, e)
                if self.retries >= self.config.max_retries:
                    raise
                time.sleep(self.config.retry_delay)
        return {}

    def _perform_scraping(self, driver: WebDriver) -> Dict[str, int]:
        """Core scraping operations"""
        driver.get(self.config.base_url)
        self._handle_popups(driver)
        
        # Original working click logic
        self._click_element(driver, "//div[3]/div/div/div/img")
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        return self._parse_prizes(soup)

    def _handle_popups(self, driver: WebDriver):
        """Popup handling from original version"""
        try:
            WebDriverWait(driver, 8).until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, "div.modal.bannerPopup")
                )
            )
        except TimeoutException:
            pass

    def _click_element(self, driver: WebDriver, xpath: str):
        """Robust element clicking"""
        element = WebDriverWait(driver, self.config.timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        element.click()

    def _parse_prizes(self, soup: BeautifulSoup) -> Dict[str, int]:
        """Original prize parsing logic preserved"""
        prizes = {}
        elements = soup.find_all("span", class_="prize")
        
        try:
            prizes = {
                "loto": self._parse_value(elements[1].text),
                "recargado": self._parse_value(elements[2].text),
                "revancha": self._parse_value(elements[3].text),
                "desquite": self._parse_value(elements[4].text),
                "jubilazo": self._parse_value(elements[5].text) + self._parse_value(elements[6].text),
                "jubilazo_50": self._parse_value(elements[7].text) + self._parse_value(elements[8].text)
            }
        except (IndexError, AttributeError) as e:
            logger.error("Prize parsing failed: %s", e)
            raise

        return prizes

    def _parse_value(self, text: str) -> int:
        """Original value parsing logic"""
        return int(text.strip("$").replace(".", "")) * 1000000

class SheetsUpdater:
    """Google Sheets integration with essential safeguards"""
    def __init__(self, config: AppConfig):
        self.config = config
        self.service = self._authenticate()

    def _authenticate(self):
        """Secure credential handling"""
        try:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(os.environ["CREDENTIALS"]),
                scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            return build("sheets", "v4", credentials=creds)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Authentication failed: %s", e)
            raise

    def update_sheet(self, data: Dict[str, int]):
        """Data update with error handling"""
        try:
            body = {
                "values": [
                    [data["loto"]],
                    [data["recargado"]],
                    [data["revancha"]],
                    [data["desquite"]],
                    [data["jubilazo"]],
                    [0],  # multiplicar
                    [data["jubilazo_50"]]
                ]
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.config.spreadsheet_id,
                range=self.config.sheets_range,
                valueInputOption="RAW",
                body=body
            ).execute()
            
            logger.info("Successfully updated Google Sheets")
        except HttpError as e:
            logger.error("Sheets API error: %s", e)
            raise

# --------------------------
# Main Execution
# --------------------------
def main():
    """Simplified main workflow preserving original logic"""
    config = AppConfig.from_env()
    
    try:
        # Scrape prizes
        scraper = PrizeScraper(config)
        prizes = scraper.scrape_prizes()
        
        # Update sheets
        SheetsUpdater(config).update_sheet(prizes)
        
        logger.info("Process completed successfully")
    except Exception as e:
        logger.critical("Fatal error: %s", e)
        raise

if __name__ == "__main__":
    main()