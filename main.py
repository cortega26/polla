from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
  
options = Options()
options.headless = True
driver = webdriver.Chrome(options=options)
driver.get("http://www.polla.cl/es")
driver.find_element("xpath", "//div[3]/div/div/div/img").click()
text = BeautifulSoup(driver.page_source, "html.parser")
prize_elements = text.find_all("span", class_="prize")
numbers = []
for prize_element in prize_elements:
    numbers.append(prize_element.text.strip("$"))
print(numbers)
driver.close()
