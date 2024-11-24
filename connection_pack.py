from datetime import datetime
import os
import uuid
import json
from binance.client import Client
import math
import logging
import time

global client

# Define get_connection outside the class
def get_connection():
    try:
        # Load credentials from JSON file
        with open('../credentials.json', 'r') as file:
            binance_credentials = json.load(file)
            api_key = binance_credentials['api_key']
            api_secret = binance_credentials['api_secret']

        # Initialize the Binance client
        client = Client(api_key, api_secret)
        client.ping()  # Ensure connection
        client.get_server_time() # getting server time from binance
        client.timestamp_offset = client.get_server_time()['serverTime'] - int(time.time() * 1000) # Enable time synchronization
        return client
    
    except FileNotFoundError:
        logging.FileNotFoundError("Error: credentials.json file not found. Please check the file path.")
    except KeyError:
        logging.KeyError("Error: Invalid format in credentials.json. Missing 'api_key' or 'api_secret'.")
    except Exception as e:
        logging.exception(f"Binance connection error, check credentials or internet: {e}")
    
    return None  # Return None explicitly if the connection fails