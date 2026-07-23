import requests
import re

def extract_user_id(url: str) -> str:
    match = re.search(r"/user/show/(\d+)", url)
    if match:
        return match.group(1)
    return "invalid url"



userProfile =  input("Enter your goodreads account: ")

userId = extract_user_id(userProfile)

url = f"https://api.piratereads.com/{userId}/read"

response = requests.request("GET", url)

print(response.text)