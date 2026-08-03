import requests
import re
import json
import pandas as pd

def extract_user_id(url: str) -> str:
    match = re.search(r"/user/show/(\d+)", url)
    if match:
        return match.group(1)
    return "invalid url"



def scrape_goodreads(user_url):
    user_id = extract_user_id(user_url)
    if user_id == "invalid url":
        return None                               

    url = f"https://api.piratereads.com/{user_id}/read"
    response = requests.get(url)

    if response.status_code != 200:
        return None                                  

    return response.json()                            
