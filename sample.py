import requests, json,csv, pandas as pd
from datetime import datetime
from loggers import logger

NETBOX_TOKEN = "Token jo8vZK2AH9j0jaekrA3csSrZI0ZGBTtUlNazmHdZ"
NETBOX_URL = "https://onwy3565.cloud.netboxapp.com/"
IP_ENDPOINT = "api/ipam/ip-addresses/"
DEVICES_ENDPOINT = "api/dcim/devices/"

headers = {
    "Authorization": NETBOX_TOKEN,
    "Content-Type": "application/json",
}

#fetch results from netbox api with pagination

def fetch_all(url):
    results = []
    page = 1

    while url:
        logger.info(f"Fetching page {page} from {url}")

        try: 
            response = requests.get(url, headers=headers)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            raise

        data = response.json()
        results.extend(data.get("results",[]))

        url = data.get("next")
        page += 1

    logger.info(f"Fetched {len(results)} total records")
    return results

#save json file
def save_json(results, prefix):
    filename = f"{prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"

    try:

        with open(filename, "w") as f:
            json.dump(results, f, indent=4)
        logger.info(f"Saved data to {filename}")

    except Exception as e:
        logger.error(f"Error saving data: {e}")

#save csv using pandas
def save_csv_panda(data, prefix):
        filename = f"{prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"

        try: 

            df = pd.json_normalize(data)
            df.to_csv(filename, index=False)
            logger.info(f"Saved data to {filename}")

        except Exception as e:
            logger.error(f"Error saving data: {e}")

def main():

    try:
        #export ips
        ip_url = NETBOX_URL + IP_ENDPOINT
        ip_data = fetch_all(ip_url)
        save_json(ip_data, "IPs")
        save_csv_panda(ip_data, "IPs")

        #export devices
        device_url = NETBOX_URL + DEVICES_ENDPOINT
        device_data = fetch_all(device_url)
        save_json(device_data, "Devices")
        save_csv_panda(device_data, "Devices")

        logger.info("Export completed successfully")
    
    except Exception as e:
        logger.error(f"Export failed: {e}")

if __name__ == "__main__":
    main()