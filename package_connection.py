from binance.client import Client
import logging
import json
import time

# Define get_connection outside the class
def get_connection():
    try:
        with open('../credentials.json', 'r') as file:
            binance_credentials = json.load(file)
            api_key = binance_credentials['api_key']
            api_secret = binance_credentials['api_secret']

        # Initialize the Binance client
        client = Client(api_key, api_secret)
        client.ping()  # Ensure connection
        client.get_server_time()  # getting server time from binance
        client.timestamp_offset = client.get_server_time()['serverTime'] - int(time.time() * 1000)  # Enable time synchronization
        return client

    except Exception as e:
        logging.exception(f"Binance connection error, check credentials or internet: {e}")

client = get_connection() #initializing client as global variable
