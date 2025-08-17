import requests
import json
from datetime import datetime

# ======================================================
# Add your API token here (replace this with your token)
API_TOKEN = "df2krm2gotjhxqwtbqrdxn6babhw8o5619wv9stu"
# ======================================================

def check_proxies():
    """
    Fetch and display available proxy IPs from Webshare API
    """
    # Base URL for the API
    base_url = "https://proxy.webshare.io/api/v2/proxy/list/"
    
    # Headers with authentication
    headers = {
        "Authorization": f"Token {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Parameters for pagination and required fields
    params = {
        "page": 1,
        "page_size": 25,  # Default page size according to docs
        "mode": "direct"  # Adding the mode parameter that seems to be required
    }
    
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching proxy list...")
        response = requests.get(base_url, headers=headers, params=params)
        
        # Check for rate limiting
        if response.status_code == 429:
            print("Rate limit exceeded. Please wait 60 seconds before trying again.")
            return
        
        # Check for other errors
        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            return
        
        # Parse the response
        data = response.json()
        
        # Display information about pagination
        print(f"Total proxies available: {data.get('count', 0)}")
        print(f"Showing page {params['page']} with {len(data.get('results', []))} proxies")
        print("-" * 80)
        
        # Display proxy information
        print(f"{'IP Address':<15} {'Port':<6} {'Country':<10} {'City':<15} {'Username':<15} {'Valid':<6}")
        print("-" * 80)
        
        for proxy in data.get("results", []):
            print(f"{proxy.get('proxy_address', 'N/A'):<15} "
                  f"{proxy.get('port', 'N/A'):<6} "
                  f"{proxy.get('country_code', 'N/A'):<10} "
                  f"{proxy.get('city_name', 'N/A')[:15]:<15} "
                  f"{proxy.get('username', 'N/A'):<15} "
                  f"{str(proxy.get('valid', False)):<6}")
        
        # Check if there are more pages
        if data.get("next"):
            print("\nMore proxies available. Use pagination to view more.")
            print(f"Next page URL: {data.get('next')}")
    
    except requests.exceptions.ConnectionError:
        print("Connection error. Please check your internet connection.")
    except json.JSONDecodeError:
        print("Error parsing response. The API returned an invalid JSON.")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")

def main():
    if API_TOKEN == "YOUR_API_TOKEN_HERE":
        print("Please update the API_TOKEN variable in the script with your actual token")
        print("You can find your API token in your Webshare dashboard")
        return
    
    check_proxies()

if __name__ == "__main__":
    main()