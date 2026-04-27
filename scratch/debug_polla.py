from scrapling import StealthyFetcher

def debug_polla():
    fetcher = StealthyFetcher(headless=True)
    shared_data = {}

    def action(page):
        try:
            page.locator("text=VER DETALLE POR CATEGORÍA").first.click(timeout=5000)
            page.wait_for_timeout(2000)
        except Exception:
            pass
        shared_data["html"] = page.content()

    fetcher.fetch("https://www.polla.cl/es/", page_action=action)
    with open("scratch/polla.html", "w") as f:
        f.write(shared_data.get("html", ""))
    print("HTML saved to scratch/polla.html")

if __name__ == "__main__":
    debug_polla()
