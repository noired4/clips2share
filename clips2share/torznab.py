import time
import requests
import xml.etree.ElementTree as ET

def poll_for_torrent(name, torznab_url, expected_title, poll_interval=30, max_retries=50):
    search_url = f"{torznab_url}&t=search&q={requests.utils.quote(expected_title)}"

    attempt = 0
    while attempt < max_retries:        
        time.sleep(poll_interval)
        try:
            response = requests.get(search_url)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title = item.find("title").text
                link = item.find("link").text
                if expected_title in title:
                    return link
        except Exception as e:
            print(f"Polling {name} failed: {e}")
        
        attempt += 1
        if attempt < max_retries - 1:
            print(f"No match found. Retrying in {poll_interval} seconds...")
        else:
            print("No match found.")

    raise TimeoutError(f"Max retries reached. No matching torrent found for {expected_title}.")