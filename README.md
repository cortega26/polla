# Polla Scraper

This script scrapes prizes from the [polla.cl](http://www.polla.cl/es) website and updates a Google Sheets spreadsheet with the scraped values.

## Requirements

- [BeautifulSoup](https://pypi.org/project/beautifulsoup4/)
- [Selenium](https://pypi.org/project/selenium/)
- [google-auth](https://pypi.org/project/google-auth/)
- [google-auth-oauthlib](https://pypi.org/project/google-auth-oauthlib/)
- [google-auth-httplib2](https://pypi.org/project/google-auth-httplib2/)
- [google-api-python-client](https://pypi.org/project/google-api-python-client/)
- [ChromeDriver](https://chromedriver.chromium.org/)

## Usage

1. Download and install the required libraries.
2. Download and install ChromeDriver.
3. Create a service account JSON file and save it as `service-account.json` in the same directory as the script.
4. Get the Google Sheets spreadsheet ID and update the `spreadsheet_id` variable in the script.
5. Run the script: `python main.py`

## Notes

- The script uses Chrome in headless mode (i.e. without a GUI) to load the website and retrieve the data.
- The `scrape_polla` function scrapes the prizes from the website using BeautifulSoup and returns a list of integers.
- The `update_google_sheet` function authenticates using the service account JSON file, builds the Sheets API client, and updates the specified range in the spreadsheet with the values from the `scrape_polla` function.
