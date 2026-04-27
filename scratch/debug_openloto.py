from scrapling import StealthyFetcher
from bs4 import BeautifulSoup

def debug_openloto():
    fetcher = StealthyFetcher(headless=True)
    response = fetcher.fetch("https://www.openloto.cl/pozo-del-loto.html")
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    
    print("--- OPENLOTO TEXT ---")
    print(text[:2000])

if __name__ == "__main__":
    debug_openloto()
