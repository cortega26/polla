"""
Polla.cl Prize Scraper (Local Test Version)
Scrapes lottery prize information.
Run locally with: python main_local.py
"""

import json
import random
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from os import environ

# Load environment variables from .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import tenacity
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from logging import getLogger, INFO, FileHandler, StreamHandler, Formatter
import chromedriver_autoinstaller

# --- Constants ---
SCRAPER_RETRY_MULTIPLIER = 1
SCRAPER_MIN_RETRY_WAIT = 5  # seconds
SCRAPER_MAX_ATTEMPTS = 3

# --- Logger Setup ---
logger = getLogger(__name__)
logger.setLevel(INFO)
formatter = Formatter(
    '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler = StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
try:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"polla_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    logger.warning("Could not set up file logging: %s", e)
logger.propagate = False

# --- Configuration Classes ---
@dataclass(frozen=True)
class ChromeConfig:
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
    base_url: str = "http://www.polla.cl/es"
    timeout: int = 10
    retry_multiplier: int = SCRAPER_RETRY_MULTIPLIER
    min_retry_wait: int = SCRAPER_MIN_RETRY_WAIT
    max_attempts: int = SCRAPER_MAX_ATTEMPTS
    element_timeout: int = 10
    page_load_timeout: int = 30

@dataclass(frozen=True)
class AppConfig:
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    
    @classmethod
    def create_default(cls) -> 'AppConfig':
        return cls()
    
    def get_chrome_options(self) -> Dict[str, Any]:
        return {k: v for k, v in self.chrome.__dict__.items() if not k.startswith('_')}

# --- Custom Exception ---
class ScriptError(Exception):
    def __init__(self, message: str, original_error: Optional[Exception] = None,
                 error_code: Optional[str] = None):
        self.message = message
        self.original_error = original_error
        self.error_code = error_code
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc() if original_error else None
        super().__init__(self.get_error_message())
    
    def get_error_message(self) -> str:
        base_msg = f"[{self.error_code}] {self.message}" if self.error_code else self.message
        if self.original_error:
            return f"{base_msg} Original error: {str(self.original_error)}"
        return base_msg
    
    def log_error(self, logger) -> None:
        logger.error("Error occurred at %s", self.timestamp.isoformat())
        logger.error("Message: %s", self.message)
        if self.error_code:
            logger.error("Error code: %s", self.error_code)
        if self.original_error:
            logger.error("Original error: %s", str(self.original_error), exc_info=True)
        if self.traceback:
            logger.error("Traceback:\n%s", self.traceback)

# --- Data Model ---
@dataclass(frozen=True)
class PrizeData:
    loto: int
    recargado: int
    revancha: int
    desquite: int
    jubilazo: int
    multiplicar: int
    jubilazo_50: int
    
    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if value < 0:
                raise ValueError(f"Prize amount cannot be negative: {field_name}={value}")
    
    def to_list(self) -> List[int]:
        return [self.loto, self.recargado, self.revancha, self.desquite,
                self.jubilazo, self.multiplicar, self.jubilazo_50]

# --- Browser Manager ---
class BrowserManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._driver: Optional[WebDriver] = None
    
    def _configure_chrome_options(self) -> webdriver.ChromeOptions:
        chrome_options = webdriver.ChromeOptions()
        for key, value in self.config.get_chrome_options().items():
            flag = f"--{key.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    chrome_options.add_argument(flag)
            else:
                chrome_options.add_argument(f"{flag}={value}")
        
        # Options to reduce bot detection
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Diverse user agents
        USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
            "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0) Gecko/20100101 Firefox/45.0",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0",
            "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.15",
            "Mozilla/5.0 (iPad; CPU OS 13_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.2 Mobile/15E148 Safari/604.1"
        ]
        chosen_user_agent = random.choice(USER_AGENTS)
        chrome_options.add_argument(f"user-agent={chosen_user_agent}")
        logger.info("Using user-agent: %s", chosen_user_agent)
        
        # Optionally disable headless mode via env variable
        if environ.get("DISABLE_HEADLESS", "false").lower() == "true":
            logger.info("DISABLE_HEADLESS set to true; running in non-headless mode.")
        else:
            if not any("headless" in arg for arg in chrome_options.arguments):
                chrome_options.add_argument("--headless")
        
        logger.debug("Chrome options: %s", chrome_options.arguments)
        return chrome_options

    def get_driver(self) -> WebDriver:
        try:
            if not self._driver:
                chromedriver_autoinstaller.install()
                options = self._configure_chrome_options()
                self._driver = webdriver.Chrome(options=options)
                self._driver.set_page_load_timeout(self.config.scraper.page_load_timeout)
            return self._driver
        except Exception as e:
            raise ScriptError("Failed to create browser instance", e, "BROWSER_INIT_ERROR")

    def close(self) -> None:
        try:
            if self._driver:
                self._driver.quit()
                self._driver = None
        except Exception as e:
            logger.warning("Error closing browser: %s", e, exc_info=True)

    def __enter__(self) -> 'BrowserManager':
        self.get_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

# --- Scraper Class ---
class PollaScraper:
    def __init__(self, config: AppConfig, browser_manager: BrowserManager) -> None:
        self.config = config
        self.browser_manager = browser_manager
        self._driver: Optional[WebDriver] = None
        self._wait: Optional[WebDriverWait] = None

    def _initialize_driver(self) -> None:
        self._driver = self.browser_manager.get_driver()
        self._wait = WebDriverWait(self._driver, self.config.scraper.element_timeout)
    
    def _save_screenshot(self, driver: WebDriver, prefix: str = "debug_screenshot") -> str:
        timestamp = int(time.time() * 1000)
        filename = f"{prefix}_{timestamp}.png"
        try:
            driver.save_screenshot(filename)
            logger.info("Screenshot saved to %s", filename)
        except Exception as se:
            logger.error("Failed to save screenshot: %s", se)
        return filename

    def _check_access_denied(self) -> None:
        page = self._driver.page_source
        if "Access Denied" in page or "Error 16" in page:
            logger.error("Access Denied detected in page source.")
            raise ScriptError("Access Denied - The website blocked the automated request.", error_code="ACCESS_DENIED")

    def _close_popup(self) -> None:
        """Closes the popup banner if present."""
        try:
            # Wait up to 5 seconds for the popup to become clickable
            popup = WebDriverWait(self._driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.close[data-bind="click: hideBanner"]'))
            )
            popup.click()
            logger.info("Popup closed successfully.")
            time.sleep(1)  # Allow the page to update
        except Exception as e:
            logger.info("Popup not found or could not be closed; continuing. (%s)", e)

    def _wait_and_click(self, css_selector: str) -> Optional[WebElement]:
        try:
            logger.debug("Current URL: %s", self._driver.current_url)
            logger.debug("Page source snippet (first 500 chars): %s", self._driver.page_source[:500])
            elements = self._driver.find_elements(By.CSS_SELECTOR, css_selector)
            logger.debug("Found %d elements matching CSS selector '%s'", len(elements), css_selector)
            element = self._wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, css_selector)))
            logger.debug("Primary element located and visible: %s", element)
            self._driver.execute_script("arguments[0].scrollIntoView(true);", element)
            logger.debug("Scrolled primary element into view.")
            time.sleep(2)
            ActionChains(self._driver).move_to_element(element).click().perform()
            logger.info("Clicked element with primary CSS selector: %s", css_selector)
            return element
        except Exception as e:
            logger.exception("Primary selector '%s' failed.", css_selector)
            self._save_screenshot(self._driver, prefix="primary_failure")
            fallback_selector = "div.expanse-controller img"
            try:
                logger.info("Attempting fallback selector: '%s'", fallback_selector)
                elements_fb = self._driver.find_elements(By.CSS_SELECTOR, fallback_selector)
                logger.debug("Found %d elements matching fallback selector '%s'", len(elements_fb), fallback_selector)
                element_fb = self._wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, fallback_selector)))
                logger.debug("Fallback element located and visible: %s", element_fb)
                self._driver.execute_script("arguments[0].scrollIntoView(true);", element_fb)
                logger.debug("Scrolled fallback element into view.")
                time.sleep(2)
                ActionChains(self._driver).move_to_element(element_fb).click().perform()
                logger.info("Clicked element with fallback CSS selector: %s", fallback_selector)
                return element_fb
            except Exception as fb_e:
                logger.exception("Fallback selector '%s' also failed.", fallback_selector)
                self._save_screenshot(self._driver, prefix="fallback_failure")
                raise ScriptError("Both primary and fallback clickable elements not found", fb_e, "ELEMENT_INTERACTION_ERROR")

    def _parse_prize(self, text: str) -> int:
        try:
            cleaned_text = text.strip("$").replace(".", "").replace(",", "").strip()
            if not cleaned_text:
                raise ValueError("Empty prize value")
            return int(cleaned_text) * 1000000
        except (ValueError, AttributeError) as e:
            logger.error("Failed to parse prize value: '%s'", text, exc_info=True)
            raise ScriptError(f"Parsing error for prize value: '{text}'", e, "PRIZE_PARSING_ERROR")

    def _validate_prizes(self, prizes: List[int]) -> None:
        if not prizes:
            raise ScriptError("No prizes found", error_code="NO_PRIZES_ERROR")
        if len(prizes) < 9:
            raise ScriptError(f"Invalid prize data: expected 9+ prizes, got {len(prizes)}", error_code="INSUFFICIENT_PRIZES_ERROR")
        if all(prize == 0 for prize in prizes):
            raise ScriptError("All prizes are zero - possible scraping error", error_code="ZERO_PRIZES_ERROR")

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=SCRAPER_RETRY_MULTIPLIER, min=SCRAPER_MIN_RETRY_WAIT),
        stop=tenacity.stop_after_attempt(SCRAPER_MAX_ATTEMPTS),
        retry=tenacity.retry_if_exception_type(ScriptError),
        before_sleep=lambda retry_state: logger.warning(
            "Scraper: Retrying in %.2f seconds (attempt %d)...", retry_state.next_action.sleep, retry_state.attempt_number),
        after=lambda retry_state: logger.info("Scraper: Attempt %d %s", retry_state.attempt_number,
                                               "succeeded" if not retry_state.outcome.failed else "failed")
    )
    def scrape(self) -> PrizeData:
        try:
            self._initialize_driver()
            logger.info("Accessing URL: %s", self.config.scraper.base_url)
            self._driver.get(self.config.scraper.base_url)
            logger.debug("Page loaded. Current URL: %s", self._driver.current_url)
            self._close_popup()  # Close the popup if present
            self._check_access_denied()
            logger.debug("Page source snippet (first 500 chars): %s", self._driver.page_source[:500])
            if not self._wait_and_click(".expanse-controller > img:nth-child(1)"):
                raise ScriptError("Failed to interact with required elements", error_code="ELEMENT_INTERACTION_ERROR")
            self._check_access_denied()
            # Wait for prize elements to load (expect at least 9 elements)
            try:
                WebDriverWait(self._driver, 15).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, "span.prize")) >= 9
                )
            except Exception as wait_exc:
                found = len(self._driver.find_elements(By.CSS_SELECTOR, "span.prize"))
                logger.error("Timeout waiting for at least 9 prize elements. Found only %d elements.", found)
                raise ScriptError("Timeout waiting for sufficient prize elements", wait_exc, "NO_PRIZES_TIMEOUT")
            soup = BeautifulSoup(self._driver.page_source, "html.parser")
            prize_elements = soup.find_all("span", class_="prize")
            logger.info("Found %d prize elements", len(prize_elements))
            prizes = [self._parse_prize(prize.text) for prize in prize_elements]
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
        except ScriptError:
            raise
        except Exception as error:
            raise ScriptError("Scraping failed", error, "SCRAPE_ERROR")
        finally:
            pass

# --- Main Application ---
class PollaApp:
    def __init__(self) -> None:
        self.config = AppConfig.create_default()
        self.browser_manager = BrowserManager(self.config)
        self.scraper = PollaScraper(self.config, self.browser_manager)

    def run(self) -> None:
        start_time = datetime.now()
        logger.info("Script started at %s", start_time.isoformat())
        try:
            with self.browser_manager:
                prize_data = self.scraper.scrape()
                logger.info("Successfully scraped prize data.")
                logger.info("Prize Data: %s", prize_data.to_list())
        except ScriptError as error:
            error.log_error(logger)
        except Exception as error:
            logger.exception("Unexpected error occurred")
            raise
        finally:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info("Script completed in %.2f seconds", duration)

def main() -> None:
    try:
        app = PollaApp()
        app.run()
    except Exception as error:
        logger.critical("Fatal error occurred: %s", str(error), exc_info=True)
        raise

if __name__ == "__main__":
    main()
