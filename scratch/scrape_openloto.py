import requests
from bs4 import BeautifulSoup
import re

def scrape_openloto():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    url = "https://www.openloto.cl/pozo-del-loto.html"
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    
    print("--- OPENLOTO TEXT SNIPPET ---")
    print(text[:2000])
    
    # Search for Sorteo and Fecha
    sorteo_re = re.compile(r"Sorteo\s*(?:N[°º]|#|:)?\s*(\d{4,})", re.IGNORECASE)
    date_re = re.compile(r"(\d{1,2})\s+de\s+([a-zA-Z]+)\s+de\s+(\d{4})", re.IGNORECASE)
    date_alt_re = re.compile(r"([a-zA-Z]+)\s+(\d{1,2}),\s+(\d{4})", re.IGNORECASE)
    
    print("\nMATCHES:")
    print(f"Sorteo: {sorteo_re.findall(text)}")
    print(f"Date: {date_re.findall(text)}")
    print(f"Date Alt: {date_alt_re.findall(text)}")

if __name__ == "__main__":
    scrape_openloto()
