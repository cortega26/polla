# Prize Scraper for polla.cl

This script is designed to scrape the prize information from [polla.cl](http://www.polla.cl/es), update the relevant values in a Google Sheet, and log the number of cells updated.

## Libraries Used

- `bs4` (Beautiful Soup): Used to parse the HTML source code of the website.
- `selenium`: Used to interact with the website and retrieve the HTML source code.
- `googleapiclient`: Used to interact with the Google Sheets API.
- `google.oauth2.service_account`: Used to authenticate the script with the Google Sheets API.
- `os`: Used to retrieve an environment variable.
- `logging`: Used for improved error reporting and logging.
- `tenacity`: Implements retry logic for robust web scraping.

## Usage

- **Install the required libraries:**

  ```sh
  pip install bs4 selenium google-api-python-client google-auth tenacity
  ```

- **Install ChromeDriver:**

  - Download and install ChromeDriver.
  - Ensure ChromeDriver is in your PATH or specify its location in the script.

- **Set Up Google Service Account:**

  - Create a service account in the Google Cloud Console.
  - Download the service account JSON file.

- **Set Environment Variable:**

  Set the CREDENTIALS environment variable to the contents of your service account JSON file.

  ```sh
  export CREDENTIALS=$(cat path/to/service-account.json)
  ```

- **Update Spreadsheet ID:**

  - Update the `SPREADSHEET_ID` variable in the script with your Google Sheets spreadsheet ID.

- **Run the script:**

  - `python main.py`

## Notes

- **Google Sheet Configuration:**
  - The script is set up to use a specific Google Sheet and range. Adjust the `SPREADSHEET_ID` and range variables as necessary.
  
- **Scheduling:**
  - The script can be scheduled to run after every lottery draw using GitHub Actions or cron jobs to ensure data in the spreadsheet is always up to date.

- **Headless Mode:**
  - The script runs in headless mode by default, meaning the Chrome window will not be visible. This can be adjusted in the `get_chrome_options` function if necessary.

- **Logging:**
  - Detailed error messages are logged to `app.log` using Python's built-in logging module for improved error reporting and debugging.

- **Robustness:**
  - The script gracefully handles exceptions during web scraping and Google Sheets update operations, ensuring robustness and reliability.
