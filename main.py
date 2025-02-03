"""
GitHub Actions-Optimized Polla.cl Scraper
Maintains full functionality with CI-specific improvements
"""

import os
import json
import logging
import tenacity
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Logging Configuration (CI-Adaptive)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File logging only in non-CI environments
if "GITHUB_ACTIONS" not in os.environ:
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(log_dir / f"polla_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"File logging disabled: {str(e)}")

logger.propagate = False

# Configuration (CI-Adaptive)
@dataclass(frozen=True)
class AppConfig:
    chrome_headless: bool = True
    chrome_timeout: int = 45
    spreadsheet_id: str = os.getenv("SPREADSHEET_ID", "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc")
    sheets_range: str = "Sheet1!A1:A7"

class ScriptError(Exception):
    """CI-optimized error handling"""
    def __init__(self, message: str, context: dict = None):
        self.message = message
        self.context = context or {}
        self.timestamp = datetime.now().isoformat()
        super().__init__(self.message)
        
    def log_error(self):
        logger.error(f"[ERROR] {self.message}")
        logger.error(f"Context: {json.dumps(self.context, indent=2)}")

@dataclass(frozen=True)
class PrizeData:
    """Full data preservation"""
    loto: int
    recargado: int
    revancha: int
    desquite: int
    jubilazo: int
    multiplicar: int
    jubilazo_50: int

    def __post_init__(self):
        for field, value in self.__dict__.items():
            if value < 0:
                raise ValueError(f"Invalid {field}: {value}")

    def to_sheet_data(self) -> List[List[int]]:
        return [
            [self.loto],
            [self.recargado],
            [self.revancha],
            [self.desquite],
            [self.jubilazo],
            [self.multiplicar],
            [self.jubilazo_50]
        ]

class BrowserManager:
    """CI-optimized browser management"""
    def __init__(self, config: AppConfig):
        self.config = config
        self.driver = self._create_driver()

    def _create_driver(self) -> webdriver.Chrome:
        options = webdriver.ChromeOptions()
        if self.config.chrome_headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,720")
        return webdriver.Chrome(options=options)

    def close(self):
        if self.driver:
            self.driver.quit()

class PollaScraper:
    """Full-featured scraper with CI optimizations"""
    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.driver = browser.driver
        self.wait = WebDriverWait(self.driver, 30)

    @tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(10))
    def scrape(self) -> PrizeData:
        try:
            self.driver.get("https://www.polla.cl/es")
            self._handle_popups()
            self._click_prize_button()
            return self._extract_prizes()
        except Exception as e:
            self.browser.close()
            raise ScriptError("Scraping failed", {"url": self.driver.current_url})

    def _handle_popups(self):
        try:
            WebDriverWait(self.driver, 10).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.modal"))
            )
        except TimeoutException:
            pass

    def _click_prize_button(self):
        button = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'prize-button')]"))
        )
        button.click()

    def _extract_prizes(self) -> PrizeData:
        elements = self.wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "span.prize"))
        )
        values = [self._parse_value(el.text) for el in elements[1:9]]  # Original indices
        
        return PrizeData(
            loto=values[0],
            recargado=values[1],
            revancha=values[2],
            desquite=values[3],
            jubilazo=values[4] + values[5],
            multiplicar=0,
            jubilazo_50=values[6] + values[7]
        )

    def _parse_value(self, text: str) -> int:
        return int(text.strip("$").replace(".", "")) * 1000000

class SheetsUpdater:
    """Full-featured Sheets integration"""
    def __init__(self, config: AppConfig):
        self.config = config
        self.service = self._initialize_service()

    @tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_exponential(multiplier=1, min=5))
    def update(self, data: PrizeData):
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.config.spreadsheet_id,
                range=self.config.sheets_range,
                body={"values": data.to_sheet_data()},
                valueInputOption="RAW"
            ).execute()
        except HttpError as e:
            raise ScriptError("Sheets API Error", {"status": e.resp.status})

    def _initialize_service(self):
        creds = service_account.Credentials.from_service_account_info(
            json.loads(os.environ["CREDENTIALS"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return build("sheets", "v4", credentials=creds)

def main():
    """CI-optimized execution flow"""
    config = AppConfig()
    try:
        browser = BrowserManager(config)
        scraper = PollaScraper(browser)
        sheets = SheetsUpdater(config)
        
        prizes = scraper.scrape()
        sheets.update(prizes)
        logger.info("Update completed successfully")
    except ScriptError as e:
        e.log_error()
        raise
    finally:
        if 'browser' in locals():
            browser.close()

if __name__ == "__main__":
    main()