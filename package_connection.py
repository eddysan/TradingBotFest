import os
from dotenv import load_dotenv
from binance.client import Client
import logging
import json
import time

dotenv_path = os.path.join(os.path.dirname(__file__), 'config', '.credentials.env')
load_dotenv(dotenv_path) #loading credentials

# Define get_connection outside the class
def get_connection():
    try:
        is_testnet = (os.getenv('TESTNET') == 'True')
        if is_testnet:
            api_key = os.getenv('BINANCE_TEST_API_KEY')
            api_secret = os.getenv('BINANCE_TEST_API_SECRET')
        else:
            api_key = os.getenv('BINANCE_PROD_API_KEY')
            api_secret = os.getenv('BINANCE_PROD_API_SECRET')
        
        # Initialize the Binance client
        client = Client(api_key, api_secret, testnet=is_testnet)
        client.ping()  # Ensure connection
        client.get_server_time()  # getting server time from binance
        client.timestamp_offset = client.get_server_time()['serverTime'] - int(time.time() * 1000)  # Enable time synchronization
        return client

    except Exception as e:
        logging.exception(f"Binance connection error, check credentials or internet: {e}")

client = get_connection() #initializing client as global variable

