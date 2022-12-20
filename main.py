"""
Scrape prizes from polla.cl website and update a Google Sheets spreadsheet with the values.

This script uses the BeautifulSoup library to scrape the prizes from the polla.cl website, 
and the Google Sheets API to update a Google Sheets spreadsheet with the scraped values. It 
utilizes Chrome in headless mode (i.e. without a GUI) to load the website and retrieve the data.
"""


from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build


def polla():
    """
    Scrape the prizes from the polla.cl website.
    
    Returns:
        list: A list of integers representing the prizes in pesos.
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("lang=en")
    options.add_argument("start-maximized")  
    options.add_argument("disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--incognito")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    driver.get("http://www.polla.cl/es")
    driver.find_element("xpath", "//div[3]/div/div/div/img").click()
    text = BeautifulSoup(driver.page_source, "html.parser")
    prizes = text.find_all("span", class_="prize")
    driver.close()
    return [int(prize.text.strip("$").replace('.', '')) * 1000000 for prize in prizes]


def main():
    print("Starting main function")  # Debug print
    # Load the service account key file
    JSON_FILE_PATH = 'service-account.json'
    creds = service_account.Credentials.from_service_account_file(JSON_FILE_PATH)
    print(creds)  # Debug print

    # Build the Sheets API client
    service = build('sheets', 'v4', credentials=creds)
    print(service)  # Debug print

    # Set the ID of the spreadsheet to update
    spreadsheet_id = '16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc' 
    range_name = 'Sheet1!A1:A7'

    # Scrape the prizes and format the values to update
    prizes = polla()
    values = [[prizes[1]],
              [prizes[2]],
              [prizes[3]],
              [prizes[4]],
              [prizes[5] + prizes[6]],
              [0],
              [prizes[7] + prizes[8]]]
    body = {'values': values}
    print(f"Updating spreadsheet with values: {values}")  # Debug print

    # Update the spreadsheet with the new values
    response = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=range_name,
        valueInputOption='RAW', body=body).execute()
    print(response)  # Debug print
    print(f'{response["updatedCells"]} cells updated.')

                             

if __name__ == '__main__':
    main()
