# Prize Scraper for polla.cl
This script is designed to scrape the prize information from [polla.cl](http://www.polla.cl/es), update the relevant values in a Google Sheet, and log the number of cells updated.

## Libraries Used
- `bs4` (Beautiful Soup): Used to parse the HTML source code of the website.
- `selenium`: Used to interact with the website and retrieve the HTML source code.
- `googleapiclient`: Used to interact with the Google Sheets API.
- `google.oauth2.service_account`: Used to authenticate the script with the Google Sheets API.
- `os`: Used to retrieve an environment variable.
- `sys`: Used to exit the script if necessary.
- `time`: Used to introduce a sleep period in case of temporary errors.

## Usage

1. Download and install the required libraries.
2. Download and install ChromeDriver.
3. Create a service account JSON file and save it as `service-account.json` in the same directory as the script.
4. Get the Google Sheets spreadsheet ID and update the `spreadsheet_id` variable in the script.
5. Run the script: `python main.py`

## Notes
- The script is set up to use a specific Google Sheet and range. This can be adjusted in the code as necessary.
- The script is set up to run after every draw of the lottery, which occurs three times a week: using GitHub Actions and cron the script is set to run at a specified time, ensuring that the data in the spreadsheet is always up to date.
- The script is set up to run in headless mode, meaning that the Chrome window will not be visible. This can be adjusted in the code as necessary.
- The script is set up to only scrape the prizes and update the relevant values in the Google Sheet. If additional information is desired, the code can be adjusted as necessary.
