"""
Polla.cl Prize Scraper and Google Sheets Updater
Scrapes lottery prize information and updates a Google Sheet with the results.
This version is designed for GitHub Actions with enhanced anti-detection measures.
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

import tenacity
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver import ActionChains
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
import chromedriver_autoinstaller
import random
import string

try:
    from selenium_stealth import stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("selenium-stealth not available. Installing...")
    import subprocess
    subprocess.check_call(["pip", "install", "selenium-stealth"])
    from selenium_stealth import stealth
    STEALTH_AVAILABLE = True

# --- Constants for retry settings ---
SCRAPER_RETRY_MULTIPLIER = 1.5  # Increased for more patience
SCRAPER_MIN_RETRY_WAIT = 10  # seconds (increased)
SCRAPER_MAX_ATTEMPTS = 5  # Increased attempts

# --- Logger configuration ---
logger = getLogger(__name__)
logger.setLevel(INFO)
formatter = Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                      datefmt='%Y-%m-%d %H:%M:%S')
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

# --- Human-like behavior utilities ---
def random_delay(min_seconds=1, max_seconds=3):
    """Add random delay to simulate human behavior"""
    time.sleep(random.uniform(min_seconds, max_seconds))

def human_like_scroll(driver, scroll_amount=None):
    """Perform human-like scrolling"""
    if scroll_amount is None:
        # Random scroll between 100-800 pixels
        scroll_amount = random.randint(100, 800)
    
    # Scroll gradually with small steps
    steps = random.randint(4, 8)
    for step in range(1, steps + 1):
        current_scroll = int(scroll_amount * (step / steps))
        driver.execute_script(f"window.scrollTo(0, {current_scroll});")
        random_delay(0.1, 0.3)

def random_movements(driver, element=None):
    """Generate random mouse movements"""
    actions = ActionChains(driver)
    
    # If no target element, move randomly on page
    if element is None:
        viewport_width = driver.execute_script("return window.innerWidth;")
        viewport_height = driver.execute_script("return window.innerHeight;")
        
        # Generate 2-5 random movements
        for _ in range(random.randint(2, 5)):
            x = random.randint(10, viewport_width - 10)
            y = random.randint(10, viewport_height - 10)
            actions.move_by_offset(x, y)
            random_delay(0.1, 0.3)
            actions.perform()
            actions = ActionChains(driver)  # Reset chain
    else:
        # Move to element with some "hesitation" movements
        element_x = element.location['x']
        element_y = element.location['y']
        
        # First move near the element
        near_x = element_x + random.randint(-20, 20)
        near_y = element_y + random.randint(-20, 20)
        actions.move_by_offset(near_x, near_y)
        actions.perform()
        random_delay(0.2, 0.5)
        
        # Then precisely to the element
        actions = ActionChains(driver)
        actions.move_to_element(element)
        actions.perform()

def generate_random_fingerprint():
    """Generate random browser fingerprint data"""
    platforms = ["Windows", "Macintosh", "Linux"]
    vendors = ["Google Inc.", "Apple Computer, Inc."]
    languages = [
        ["es-ES", "es"], 
        ["en-US", "en"], 
        ["es-CL", "es", "en-US", "en"]
    ]
    
    return {
        "platform": random.choice(platforms),
        "vendor": random.choice(vendors),
        "languages": random.choice(languages),
        "webgl_vendor": "Intel Inc.",
        "renderer": "Intel Iris OpenGL Engine",
    }

# --- Configuration Classes ---
@dataclass(frozen=True)
class ChromeConfig:
    headless: bool = True
    no_sandbox: bool = True
    disable_dev_shm_usage: bool = True
    lang: str = "es-CL,es;q=0.9,en;q=0.8"
    disable_extensions: bool = True
    incognito: bool = True
    disable_blink_features: str = "AutomationControlled"
    disable_gpu: bool = True
    window_size: str = "1920,1080"

@dataclass(frozen=True)
class ScraperConfig:
    base_url: str = "http://www.polla.cl/es"
    timeout: int = 15  # Increased timeout
    retry_multiplier: int = SCRAPER_RETRY_MULTIPLIER
    min_retry_wait: int = SCRAPER_MIN_RETRY_WAIT
    max_attempts: int = SCRAPER_MAX_ATTEMPTS
    element_timeout: int = 15  # increased timeout for slower pages
    page_load_timeout: int = 45  # Increased
    cookies_file: str = "polla_cookies.json"

@dataclass(frozen=True)
class GoogleConfig:
    spreadsheet_id: str = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
    range_name: str = "Sheet1!A1:A7"
    scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/spreadsheets",)
    retry_attempts: int = 3
    retry_delay: int = 5

@dataclass(frozen=True)
class AppConfig:
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    
    @classmethod
    def create_default(cls) -> 'AppConfig':
        return cls()
    
    def get_chrome_options(self) -> Dict[str, Any]:
        return {k: v for k, v in self.chrome.__dict__.items() if not k.startswith('_')}

# --- Custom Exception ---
class ScriptError(Exception):
    def __init__(self, message: str, original_error: Optional[Exception] = None, error_code: Optional[str] = None):
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
        return sum([self.loto, self.recargado, self.revancha, self.desquite, self.jubilazo, self.multiplicar, self.jubilazo_50])

# --- Browser Manager ---
class BrowserManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._driver: Optional[WebDriver] = None
        self.fingerprint = generate_random_fingerprint()
        
    def _generate_random_user_agent(self) -> str:
        """Generate a more convincing random user agent"""
        os_versions = {
            "Windows": ["10.0", "11.0"],
            "Macintosh": ["10_15_7", "11_2_3", "12_0_1"],
            "Linux": ["x86_64"]
        }
        
        chrome_versions = ["96.0.4664.110", "97.0.4692.71", "98.0.4758.102", "99.0.4844.51", "100.0.4896.75"]
        
        os_name = random.choice(list(os_versions.keys()))
        os_version = random.choice(os_versions[os_name])
        chrome_version = random.choice(chrome_versions)
        
        if os_name == "Windows":
            platform = f"Windows NT {os_version}"
        elif os_name == "Macintosh":
            platform = f"Macintosh; Intel Mac OS X {os_version}"
        else:
            platform = f"X11; Linux {os_version}"
            
        user_agent = f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
        return user_agent
    
    def _configure_chrome_options(self) -> webdriver.ChromeOptions:
        chrome_options = webdriver.ChromeOptions()
        
        # Add standard arguments
        for key, value in self.config.get_chrome_options().items():
            flag = f"--{key.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    chrome_options.add_argument(flag)
            else:
                chrome_options.add_argument(f"{flag}={value}")
        
        # Anti-detection measures
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Advanced fingerprinting evasion
        chrome_options.add_experimental_option("prefs", {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.images": 1,
            "profile.default_content_setting_values.cookies": 1,
            "profile.default_content_setting_values.plugins": 1,
            "profile.default_content_setting_values.popups": 2,
            "profile.default_content_setting_values.geolocation": 2,
            "profile.default_content_setting_values.auto_select_certificate": 2,
            "profile.default_content_setting_values.mixed_script": 1,
            "profile.default_content_setting_values.media_stream": 2,
            "profile.default_content_setting_values.media_stream_mic": 2,
            "profile.default_content_setting_values.media_stream_camera": 2,
            "profile.default_content_setting_values.protocol_handlers": 2,
            "profile.default_content_setting_values.midi_sysex": 2,
            "profile.default_content_setting_values.push_messaging": 2,
            "profile.default_content_setting_values.ssl_cert_decisions": 2,
            "profile.default_content_setting_values.metro_switch_to_desktop": 2,
            "profile.default_content_setting_values.protected_media_identifier": 2,
            "profile.default_content_setting_values.site_engagement": 2,
            "profile.default_content_setting_values.durable_storage": 2
        })
        
        # Generate random user agent
        user_agent = self._generate_random_user_agent()
        chrome_options.add_argument(f"user-agent={user_agent}")
        logger.info("Using user-agent: %s", user_agent)
        
        # Optionally disable headless mode via environment variable
        if environ.get("DISABLE_HEADLESS", "false").lower() == "true":
            logger.info("DISABLE_HEADLESS set to true; running in non-headless mode.")
            # Remove headless from arguments if it's there
            chrome_options.arguments = [arg for arg in chrome_options.arguments if "--headless" not in arg]
        else:
            if not any("headless" in arg for arg in chrome_options.arguments):
                chrome_options.add_argument("--headless=new")  # Use new headless mode
        
        logger.debug("Chrome options: %s", chrome_options.arguments)
        return chrome_options
    
    def save_cookies(self, path: str = None) -> None:
        """Save cookies for future sessions"""
        if not self._driver:
            logger.warning("Cannot save cookies: driver not initialized")
            return
            
        if path is None:
            path = self.config.scraper.cookies_file
            
        try:
            cookies = self._driver.get_cookies()
            with open(path, 'w') as file:
                json.dump(cookies, file)
            logger.info("Saved %d cookies to %s", len(cookies), path)
        except Exception as e:
            logger.warning("Failed to save cookies: %s", e)
    
    def load_cookies(self, path: str = None) -> bool:
        """Load cookies from a previous session"""
        if not self._driver:
            logger.warning("Cannot load cookies: driver not initialized")
            return False
            
        if path is None:
            path = self.config.scraper.cookies_file
            
        try:
            cookie_file = Path(path)
            if not cookie_file.exists():
                logger.info("No cookies file found at %s", path)
                return False
                
            with open(path, 'r') as file:
                cookies = json.load(file)
                
            # Execute a blank get first to be able to add cookies
            current_url = self._driver.current_url
            if current_url == "data:,":  # Empty page
                self._driver.get("https://www.polla.cl")
                
            for cookie in cookies:
                # Remove problematic attributes
                if 'expiry' in cookie:
                    del cookie['expiry']
                try:
                    self._driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug("Could not add cookie %s: %s", cookie.get('name'), e)
                    
            logger.info("Loaded %d cookies from %s", len(cookies), path)
            return True
        except Exception as e:
            logger.warning("Failed to load cookies: %s", e)
            return False

    def get_driver(self) -> WebDriver:
        try:
            if not self._driver:
                chromedriver_autoinstaller.install()
                options = self._configure_chrome_options()
                self._driver = webdriver.Chrome(options=options)
                self._driver.set_page_load_timeout(self.config.scraper.page_load_timeout)
                
                # Apply stealth settings
                if STEALTH_AVAILABLE:
                    fp = self.fingerprint
                    stealth(
                        self._driver,
                        languages=fp["languages"],
                        vendor=fp["vendor"],
                        platform=fp["platform"],
                        webgl_vendor=fp["webgl_vendor"],
                        renderer=fp["renderer"],
                        fix_hairline=True,
                    )
                    logger.info("Applied stealth settings with fingerprint: %s", fp)
                    
                # Additional Anti-Detection via CDP
                self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // Overwrite the 'plugins' property to use a custom getter
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            // Create a few fake plugins
                            const fakePlugins = [
                                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: 'Portable Document Format' }
                            ];
                            
                            const mockPlugins = fakePlugins.map(plugin => {
                                const pluginObj = {
                                    name: plugin.name,
                                    filename: plugin.filename,
                                    description: plugin.description
                                };
                                
                                return pluginObj;
                            });
                            
                            return Object.defineProperties(
                                [],
                                {
                                    ...mockPlugins.reduce((acc, plugin, idx) => {
                                        acc[idx] = {
                                            value: plugin,
                                            enumerable: true
                                        };
                                        return acc;
                                    }, {}),
                                    length: {
                                        value: mockPlugins.length,
                                        enumerable: true
                                    }
                                }
                            );
                        }
                    });
                    
                    // Overwrite the 'languages' property
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['es-CL', 'es', 'en-US', 'en']
                    });
                    
                    // Fake the hardware concurrency (CPU cores)
                    Object.defineProperty(navigator, 'hardwareConcurrency', {
                        get: () => 8
                    });
                    
                    // Fake the connection info
                    if (navigator.connection) {
                        Object.defineProperties(navigator.connection, {
                            rtt: { get: () => 50 },
                            downlink: { get: () => 10 },
                            effectiveType: { get: () => '4g' }
                        });
                    }
                    
                    // Hide automation-related properties
                    const originalGetElementById = document.getElementById;
                    document.getElementById = function(id) {
                        if (id === 'selenium-ide-indicator') {
                            return null;
                        }
                        return originalGetElementById.apply(document, arguments);
                    };
                    """
                })
                
                logger.info("ChromeDriver initialized with enhanced anti-detection measures")
                
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
        deny_indicators = [
            "Access Denied", 
            "Error 16", 
            "Request blocked", 
            "Imperva", 
            "Security check",
            "Please wait while we verify",
            "Your request has been blocked",
            "DDoS protection",
            "Bot Detection"
        ]
        
        for indicator in deny_indicators:
            if indicator in page:
                logger.error("Access Denied detected in page source: %s", indicator)
                self._save_screenshot(self._driver, prefix="access_denied")
                raise ScriptError(f"Access Denied - {indicator} detected", error_code="ACCESS_DENIED")

    def _close_popup(self) -> None:
        """Close the popup banner if it appears."""
        try:
            # Wait longer for popups to appear
            time.sleep(random.uniform(5, 10))
            
            # Try multiple potential popup selectors
            popup_selectors = [
                'span.close[data-bind="click: hideBanner"]',
                '.banner-close',
                '.modal-close',
                '.popup-close',
                'button.close',
                'button.dismiss',
                'span.close',
                'div.close-button'
            ]
            
            for selector in popup_selectors:
                try:
                    elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        for elem in elements:
                            if elem.is_displayed():
                                # Move to the element in a human-like way
                                random_movements(self._driver, elem)
                                random_delay(0.5, 1.5)
                                elem.click()
                                logger.info(f"Popup closed successfully with selector: {selector}")
                                random_delay(1, 2)
                                return
                except Exception:
                    continue
            
            logger.info("No popups found or could not be closed; continuing.")
        except Exception as e:
            logger.info("Error handling popups: %s", e)

    def _wait_and_click(self, css_selector: str) -> Optional[WebElement]:
        try:
            # Try to find the target element first
            logger.debug("Current URL: %s", self._driver.current_url)
            logger.debug("Page source snippet (first 500 chars): %s", self._driver.page_source[:500])
            
            # Perform a human-like scroll first
            human_like_scroll(self._driver)
            random_delay(1, 2)
            
            elements = self._driver.find_elements(By.CSS_SELECTOR, css_selector)
            logger.debug("Found %d elements matching CSS selector '%s'", len(elements), css_selector)
            
            # Wait for element to be visible and clickable
            element = self._wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector)))
            logger.debug("Primary element located and clickable: %s", element)
            
            # Scroll element into view with human-like behavior
            self._driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            logger.debug("Scrolled primary element into view")
            random_delay(1, 2)
            
            # Move to the element in a human-like way before clicking
            random_movements(self._driver, element)
            random_delay(0.5, 1.5)
            
            # Click with action chains (more human-like)
            actions = ActionChains(self._driver)
            actions.move_to_element(element)
            actions.pause(random.uniform(0.1, 0.3))  # Brief pause before click
            actions.click()
            actions.perform()
            
            logger.info("Clicked element with primary CSS selector: %s", css_selector)
            random_delay(1, 3)  # Wait after clicking
            return element
        except Exception as e:
            logger.exception("Primary selector '%s' failed: %s", css_selector, e)
            self._save_screenshot(self._driver, prefix="primary_failure")
            
            # Try alternative selectors
            fallback_selectors = [
                "div.expanse-controller img",
                "div.info-games-container img",
                ".expanse-controller img",
                ".game-expanse-controller",
                ".expand-icon",
                "img[alt*='expand']"
            ]
            
            for fallback_selector in fallback_selectors:
                try:
                    logger.info("Attempting fallback selector: '%s'", fallback_selector)
                    elements_fb = self._driver.find_elements(By.CSS_SELECTOR, fallback_selector)
                    if not elements_fb:
                        logger.debug("No elements found for fallback selector '%s'", fallback_selector)
                        continue
                        
                    logger.debug("Found %d elements matching fallback selector '%s'", len(elements_fb), fallback_selector)
                    
                    for element_fb in elements_fb:
                        if not element_fb.is_displayed():
                            continue
                            
                        logger.debug("Fallback element located and visible")
                        self._driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element_fb)
                        logger.debug("Scrolled fallback element into view")
                        random_delay(1, 2)
                        
                        # Move to the element in a human-like way before clicking
                        random_movements(self._driver, element_fb)
                        random_delay(0.5, 1.5)
                        
                        # Click with action chains
                        actions = ActionChains(self._driver)
                        actions.move_to_element(element_fb)
                        actions.pause(random.uniform(0.1, 0.3))
                        actions.click()
                        actions.perform()
                        
                        logger.info("Clicked element with fallback CSS selector: %s", fallback_selector)
                        random_delay(1, 3)
                        return element_fb
                except Exception as fb_e:
                    logger.debug("Fallback selector '%s' failed: %s", fallback_selector, fb_e)
                    continue
                    
            # If all fallback selectors failed
            self._save_screenshot(self._driver, prefix="all_selectors_failed")
            raise ScriptError("All clickable element selectors failed", e, "ELEMENT_INTERACTION_ERROR")

    def _parse_prize(self, text: str) -> int:
        try:
            # More robust cleaning - handle different formats
            cleaned_text = text.strip()
            if not cleaned_text:
                raise ValueError("Empty prize value")
                
            # Remove currency symbol and non-numeric characters
            cleaned_text = cleaned_text.replace("$", "").replace(".", "").replace(",", "").strip()
            
            # Handle potential "MM" (million) abbreviation
            if "MM" in cleaned_text or "mm" in cleaned_text:
                cleaned_text = cleaned_text.replace("MM", "").replace("mm", "").strip()
                value = float(cleaned_text) * 1000000
            else:
                value = float(cleaned_text)
                
            # If value is too small, assume it's in millions
            if value < 1000 and value > 0:
                value *= 1000000
                
            return int(value)
        except (ValueError, AttributeError) as e:
            logger.error("Failed to parse prize value: '%s'", text, exc_info=True)
            raise ScriptError(f"Parsing error for prize value: '{text}'", e, "PRIZE_PARSING_ERROR")

    def _validate_prizes(self, prizes: List[int]) -> None:
        if not prizes:
            raise ScriptError("No prizes found", error_code="NO_PRIZES_ERROR")
        if len(prizes) < 7:  # Changed from 9 to 7 as minimum
            raise ScriptError(f"Invalid prize data: expected 7+ prizes, got {len(prizes)}", error_code="INSUFFICIENT_PRIZES_ERROR")
        if all(prize == 0 for prize in prizes):
            raise ScriptError("All prizes are zero - possible scraping error", error_code="ZERO_PRIZES_ERROR")

    def _bypass_imperva(self) -> bool:
        """Attempt special techniques to bypass Imperva protection."""
        try:
            logger.info("Attempting Imperva bypass techniques...")
            
            # Check for common protection challenges and forms
            challenge_selectors = [
                "form[action*='/_Incapsula_Resource']",
                "#challenge-form",
                "#captcha-form",
                "#waf-challenge-form",
                "iframe[src*='captcha']",
                "div[class*='captcha']"
            ]
            
            for selector in challenge_selectors:
                    elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and elements[0].is_displayed():
                        logger.info("Detected challenge form with selector: %s", selector)
                        self._save_screenshot(self._driver, prefix="challenge_detected")
                        
                        # Try to wait for the challenge to complete automatically
                        logger.info("Waiting for automatic challenge resolution...")
                        time.sleep(random.uniform(20, 30))  # Wait longer for auto-resolution
                        
                        # Check if we're past the challenge
                        if not any(indicator in self._driver.page_source for indicator in ["Imperva", "DDoS protection", "Security check"]):
                            logger.info("Challenge appears to be resolved")
                            return True
            
            # Additional bypass technique: simulate normal browsing behavior
            logger.info("Simulating normal browsing behavior for bypass...")
            
            # First try refreshing with a random delay
            random_delay(3, 7)
            self._driver.refresh()
            random_delay(5, 10)
            
            # Check if the refresh helped
            if not any(indicator in self._driver.page_source for indicator in ["Imperva", "Access Denied", "Bot Detection"]):
                logger.info("Refresh appears to have bypassed protection")
                return True
                
            # Try changing headers via execute_cdp_cmd
            random_user_agent = self.browser_manager._generate_random_user_agent()
            self._driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": random_user_agent})
            logger.info("Changed user agent to: %s", random_user_agent)
            
            # Try adding a random referrer
            referrers = [
                "https://www.google.cl/",
                "https://www.google.com/search?q=polla+chile",
                "https://www.bing.com/search?q=loto+chile",
                "https://www.yahoo.com/",
                "https://duckduckgo.com/"
            ]
            referrer = random.choice(referrers)
            self._driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Referer": referrer}})
            logger.info("Set referer to: %s", referrer)
            
            # Try again with a clean navigation
            self._driver.get("https://www.polla.cl")
            random_delay(5, 8)
            
            # Final check if we bypassed
            if not any(indicator in self._driver.page_source for indicator in ["Imperva", "Access Denied", "Bot Detection"]):
                logger.info("CDN/WAF protection appears to be bypassed after remediation")
                return True
                
            logger.warning("Failed to bypass protection - will attempt to continue anyway")
            return False
        except Exception as e:
            logger.error("Error during bypass attempt: %s", e)
            return False

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(ScriptError),
        wait=tenacity.wait_exponential(multiplier=SCRAPER_RETRY_MULTIPLIER, min=SCRAPER_MIN_RETRY_WAIT),
        stop=tenacity.stop_after_attempt(SCRAPER_MAX_ATTEMPTS),
        before_sleep=lambda retry_state: logger.info(f"Retrying in {retry_state.next_action.sleep} seconds...")
    )
    def scrape_prize_data(self) -> PrizeData:
        try:
            self._initialize_driver()
            logger.info("Starting prize data scraping process...")
            
            # Visit the main page with randomized approach
            attempts = 0
            max_attempts = 3
            success = False
            
            while attempts < max_attempts and not success:
                try:
                    attempts += 1
                    logger.info("Loading main page (attempt %d/%d)...", attempts, max_attempts)
                    
                    # Add random query parameters to avoid caching
                    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                    url = f"{self.config.scraper.base_url}?_={int(time.time())}&r={random_str}"
                    logger.info("Accessing URL: %s", url)
                    
                    self._driver.get(url)
                    random_delay(3, 7)  # Initial delay after page load
                    
                    # Check for access denied
                    self._check_access_denied()
                    
                    # Try to load cookies from previous session
                    self.browser_manager.load_cookies()
                    
                    # Check for popups or dialogs and close them
                    self._close_popup()
                    
                    # Simulate human browsing behavior
                    human_like_scroll(self._driver)
                    random_movements(self._driver)
                    random_delay(2, 5)
                    
                    # Check if we need to bypass security measures
                    if any(indicator in self._driver.page_source for indicator in ["Imperva", "DDoS protection", "Security check"]):
                        self._bypass_imperva()
                    
                    # Verify we have access to the content
                    if "Loto" in self._driver.page_source or "loto" in self._driver.page_source.lower():
                        success = True
                        logger.info("Main page loaded successfully")
                    else:
                        logger.warning("Page loaded but content not found, retrying...")
                        random_delay(5, 10)
                        
                except Exception as e:
                    if attempts >= max_attempts:
                        raise
                    logger.warning("Error loading main page: %s. Retrying...", e)
                    random_delay(5, 10)
            
            if not success:
                raise ScriptError("Failed to access main page after multiple attempts", error_code="MAIN_PAGE_ACCESS_ERROR")
            
            # Save cookies for future runs
            self.browser_manager.save_cookies()
            
            # Click on the expand button for each game to see prize information
            logger.info("Looking for prize information...")
            
            # Find and extract all prize data
            prizes = []
            games = ["loto", "recargado", "revancha", "desquite", "jubilazo", "multiplicar", "jubilazo_50"]
            selectors_map = {
                "loto": ["div[data-game='Loto'] .expand-icon", ".game-loto .expand-icon", ".lottery-loto .expand-button"],
                "recargado": ["div[data-game='Recargado'] .expand-icon", ".game-recargado .expand-icon", ".lottery-recargado .expand-button"],
                "revancha": ["div[data-game='Revancha'] .expand-icon", ".game-revancha .expand-icon", ".lottery-revancha .expand-button"],
                "desquite": ["div[data-game='Desquite'] .expand-icon", ".game-desquite .expand-icon", ".lottery-desquite .expand-button"],
                "jubilazo": ["div[data-game='Jubilazo'] .expand-icon", ".game-jubilazo .expand-icon", ".lottery-jubilazo .expand-button"],
                "multiplicar": ["div[data-game='Multiplicar'] .expand-icon", ".game-multiplicar .expand-icon", ".lottery-multiplicar .expand-button"],
                "jubilazo_50": ["div[data-game='Jubilazo 50'] .expand-icon", ".game-jubilazo-50 .expand-icon", ".lottery-jubilazo-50 .expand-button"]
            }
            
            prize_selectors = [
                ".prize-amount", ".prize-value", ".prize-money", 
                ".jackpot-amount", ".jackpot-value", ".jackpot",
                "span[data-bind*='prize']", "span[data-bind*='jackpot']"
            ]
                
            for game in games:
                try:
                    logger.info("Processing game: %s", game)
                    
                    # Try multiple selectors for each game
                    game_clicked = False
                    for selector in selectors_map[game]:
                        try:
                            self._wait_and_click(selector)
                            game_clicked = True
                            logger.info("Successfully clicked game: %s using selector: %s", game, selector)
                            break
                        except Exception as click_e:
                            logger.debug("Failed to click %s with selector %s: %s", game, selector, click_e)
                    
                    if not game_clicked:
                        logger.warning("Could not click on game: %s - will try to continue", game)
                    
                    # Allow time for prize data to load after click
                    random_delay(2, 4)
                    
                    # Extract prize value, trying multiple selectors
                    prize_value = None
                    for prize_selector in prize_selectors:
                        try:
                            prize_elements = self._driver.find_elements(By.CSS_SELECTOR, prize_selector)
                            if prize_elements:
                                for element in prize_elements:
                                    if element.is_displayed():
                                        prize_text = element.text or element.get_attribute("textContent")
                                        if prize_text and any(c.isdigit() for c in prize_text):
                                            prize_value = self._parse_prize(prize_text)
                                            logger.info("Extracted %s prize: %s (parsed to %d)", game, prize_text, prize_value)
                                            break
                                if prize_value is not None:
                                    break
                        except Exception as extract_e:
                            logger.debug("Failed to extract prize with selector %s: %s", prize_selector, extract_e)
                    
                    # If no prize was found, add a default value
                    if prize_value is None:
                        logger.warning("Could not extract prize for %s - using fallback value", game)
                        prize_value = 0
                    
                    prizes.append(prize_value)
                    
                except Exception as game_e:
                    logger.error("Error processing game %s: %s", game, game_e)
                    prizes.append(0)  # Add placeholder to maintain array structure
                
                # Add some delay between games to make it more human-like
                random_delay(1, 3)
            
            # Verify we got valid prizes
            if prizes:
                try:
                    self._validate_prizes(prizes)
                except ScriptError as se:
                    # If validation fails, try one last direct extraction approach
                    logger.warning("Prize validation failed: %s. Attempting direct extraction as backup.", se)
                    soup = BeautifulSoup(self._driver.page_source, 'html.parser')
                    prize_elements = soup.select(".prize-amount, .jackpot-amount, .prize-value")
                    
                    if len(prize_elements) >= 7:
                        prizes = []
                        for i, element in enumerate(prize_elements[:7]):
                            try:
                                prize_text = element.text.strip()
                                prize_value = self._parse_prize(prize_text)
                                prizes.append(prize_value)
                            except Exception:
                                prizes.append(0)
                    
                    # Validate again
                    self._validate_prizes(prizes)
            
            # Save the final state of the page for debugging
            self._save_screenshot(self._driver, prefix="final_state")
            
            # Return the prize data
            return PrizeData(
                loto=prizes[0],
                recargado=prizes[1],
                revancha=prizes[2],
                desquite=prizes[3],
                jubilazo=prizes[4],
                multiplicar=prizes[5],
                jubilazo_50=prizes[6]
            )
        except Exception as e:
            logger.error("Error during scraping: %s", str(e), exc_info=True)
            self._save_screenshot(self._driver, prefix="error_state")
            raise ScriptError("Failed to scrape prize data", e, "SCRAPE_ERROR")
        finally:
            if self._driver:
                try:
                    self.browser_manager.save_cookies()
                except Exception as cookie_e:
                    logger.warning("Error saving cookies: %s", cookie_e)

# --- Credential & Google Sheets Managers (unchanged) ---
class CredentialManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @staticmethod
    def _validate_credentials_dict(creds_dict: Dict[str, Any]) -> None:
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in creds_dict]
        if missing_fields:
            raise ScriptError(f"Missing required credential fields: {', '.join(missing_fields)}", error_code="INVALID_CREDENTIALS")

    def get_credentials(self) -> Credentials:
        try:
            credentials_json = environ.get("CREDENTIALS")
            if not credentials_json:
                logger.error("CREDENTIALS environment variable is not set")
                raise ScriptError("CREDENTIALS environment variable is empty", error_code="MISSING_CREDENTIALS")
            try:
                credentials_dict = json.loads(credentials_json)
                self._validate_credentials_dict(credentials_dict)
                logger.info("Google credentials successfully loaded and validated.")
                return service_account.Credentials.from_service_account_info(credentials_dict, scopes=self.config.google.scopes)
            except json.JSONDecodeError as e:
                preview = credentials_json[:10] + "..." if len(credentials_json) > 10 else "EMPTY"
                logger.error("Failed to parse credentials JSON. Preview: %s", preview, exc_info=True)
                raise ScriptError("Invalid JSON in CREDENTIALS environment variable", e, "INVALID_JSON")
        except Exception as error:
            if isinstance(error, ScriptError):
                raise
            raise ScriptError("Error retrieving credentials", error, "CREDENTIAL_ERROR")

class GoogleSheetsManager:
    def __init__(self, config: AppConfig, credential_manager: CredentialManager) -> None:
        self.config = config
        self.credential_manager = credential_manager
        self._service = None

    def _initialize_service(self) -> None:
        if not self._service:
            creds = self.credential_manager.get_credentials()
            self._service = build("sheets", "v4", credentials=creds)

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=5),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type((HttpError, ScriptError)),
        before_sleep=lambda retry_state: logger.warning("Google Sheets update: Retrying in %.2f seconds (attempt %d)...", retry_state.next_action.sleep, retry_state.attempt_number),
        after=lambda retry_state: logger.info("Google Sheets update: Attempt %d %s", retry_state.attempt_number, "succeeded" if not retry_state.outcome.failed else "failed")
    )
    def update_sheet(self, prize_data: PrizeData) -> None:
        try:
            self._initialize_service()
            values = prize_data.to_sheet_values()
            body = {"values": values}
            logger.info("Updating Google Sheet with prize data...")
            try:
                response = self._service.spreadsheets().values().update(
                    spreadsheetId=self.config.google.spreadsheet_id,
                    range=self.config.google.range_name,
                    valueInputOption="RAW",
                    body=body
                ).execute()
                updated = response.get('updatedCells', 0)
                logger.info("Update successful - %d cells updated. Total prizes: %d. Timestamp: %s",
                            updated, prize_data.total_prize_money, datetime.now().isoformat())
            except HttpError as error:
                status = getattr(error.resp, 'status', None)
                if status == 403:
                    raise ScriptError("Permission denied - check service account permissions", error, "PERMISSION_DENIED")
                elif status == 404:
                    raise ScriptError("Spreadsheet not found - check spreadsheet ID", error, "SPREADSHEET_NOT_FOUND")
                else:
                    raise ScriptError(f"Google Sheets API error: {status}", error, "SHEETS_API_ERROR")
        except Exception as error:
            raise ScriptError("Error updating Google Sheet", error, "UPDATE_ERROR")

# --- Main Application ---
class PollaApp:
    def __init__(self) -> None:
        self.config = AppConfig.create_default()
        self.browser_manager = BrowserManager(self.config)
        self.credential_manager = CredentialManager(self.config)
        self.sheets_manager = GoogleSheetsManager(self.config, self.credential_manager)
        self.scraper = PollaScraper(self.config, self.browser_manager)

    def run(self) -> None:
        start_time = datetime.now()
        logger.info("Script started at %s", start_time.isoformat())
        try:
            with self.browser_manager:
                prize_data = self.scraper.scrape_prize_data()
                logger.info("Successfully scraped prize data.")
                logger.info("Prize Data: %s", prize_data.to_sheet_values())
                self.sheets_manager.update_sheet(prize_data)
                logger.info("Successfully updated Google Sheet.")
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
