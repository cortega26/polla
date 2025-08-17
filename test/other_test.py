import os
import random
import requests
import logging
from typing import Optional
from os import environ

# Setup logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def fetch_proxy_from_api(api_url: str) -> Optional[str]:
    token = os.environ.get("PROXY_API_TOKEN", "").strip()
    if not token:
        logger.warning("No PROXY_API_TOKEN found in environment.")
        return None
    headers = {"Authorization": f"Token {token}"}
    try:
        logger.info("Fetching proxy list from API: %s", api_url)
        response = requests.get(api_url, headers=headers)
        logger.debug("Response status code: %s", response.status_code)
        logger.debug("Response headers: %s", response.headers)
        logger.debug("Response text: %s", response.text)
        data = response.json()
        logger.debug("Parsed JSON response: %s", data)
        if "mode" in data:
            logger.error("API error for field 'mode': %s", data["mode"])
            return None
        results = data.get("results", [])
        if results:
            chosen = random.choice(results)
            ip = chosen.get("ip")
            port = chosen.get("port")
            protocol = chosen.get("protocol", "http")
            if ip and port:
                proxy_str = f"{protocol}://{ip}:{port}"
                logger.info("Selected proxy: %s", proxy_str)
                return proxy_str
            else:
                logger.warning("Incomplete proxy details in chosen result: %s", chosen)
                return None
        else:
            logger.warning("No proxies found in API response.")
            return None
    except Exception as e:
        logger.warning("Failed to fetch or parse proxy list from API: %s", e)
        return None

if __name__ == "__main__":
    # Set environment variables for testing (replace with your actual values)
    os.environ["PROXY_API_URL"] = "https://proxy.webshare.io/api/v2/proxy/list/?mode=transparent"
    os.environ["PROXY_API_TOKEN"] = "df2krm2gotjhxqwtbqrdxn6babhw8o5619wv9stu"
    
    api_url = os.environ.get("PROXY_API_URL")
    selected_proxy = fetch_proxy_from_api(api_url)
    print("Selected proxy:", selected_proxy)
