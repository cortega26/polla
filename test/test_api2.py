import requests
from os import environ

environ["PROXY_API_TOKEN"] = "df2krm2gotjhxqwtbqrdxn6babhw8o5619wv9stu"  # set it manually for testing
api_url = "https://proxy.webshare.io/api/v2/proxy/list/?page=1&page_size=10&mode=transparent"  # try adding &mode=all if needed

headers = {"Authorization": f"Token {environ.get('PROXY_API_TOKEN').strip()}"}
response = requests.get(api_url, headers=headers)
print("Status code:", response.status_code)
print("Response headers:", response.headers)
print("Response text:", response.text)
