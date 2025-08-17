import requests
from os import environ

token = environ.get("PROXY_API_TOKEN", "").strip()
api_url = environ.get("PROXY_API_URL")
headers = {"Authorization": f"Token {token}"}

response = requests.get(api_url, headers=headers)
print(response.json())