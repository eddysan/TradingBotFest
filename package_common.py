from datetime import datetime
import os
import uuid
import json
from binance.client import Client
import math
import logging
import time

# Define get_connection outside the class
def get_connection():
    client = ''
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
    
    except Exception as e:
        logging.exception(f"Binance connection error, check credentials or internet: {e}")
    
    return None  # Return None explicitly if the connection fails


# Reading json file, the json_file_path should include directory + file + .json extension
def read_config_data(json_file_path):
    try:
        # Attempt to load file
        if os.path.isfile(json_file_path):
            with open(json_file_path, 'r') as file:
                config_file = json.load(file)
                logging.debug(f"Successfully loaded data_grid file: {json_file_path}")
                return config_file
        else:
            logging.warning(f"data_grid file '{json_file_path}' not found")
    except (FileNotFoundError, KeyError):
        logging.exception("Error: Invalid config.json file or not found. Please check the file path and format.")
        print(f"Error: Invalid {json_file_path} file or not found. Please check the file path and format.")
        return

# Writting json data grid file
def write_config_data(directory, file_name, data_grid):
    os.makedirs(directory, exist_ok=True) # if directory doesn't exist, it will be created
    xfile = f"{directory}/{file_name}" # file name should have extension to
    with open(xfile, 'w') as file:
        json.dump(data_grid, file, indent=4)  # Pretty-print JSON
    return None



# get strategy from operation file
def get_strategy(operation):
    operation_file = read_config_data(f"ops/{operation}.json")
    return operation_file['strategy']  # reading strategy type

# round price to tick size
def round_to_tick(price, tick_size):
    tick_increment = int(abs(math.log10(tick_size)))
    return round(price, tick_increment)

# getting distance between two points as percentage
def get_distance(first_point, second_point, side):
    if side == 'LONG':
        distance = round( ((float(second_point) - float(first_point)) / float(first_point)) * 100, 2)
        return distance
    if side == 'SHORT':
        distance = round( ((float(first_point) - float(second_point)) / float(first_point)) * 100, 2)
        return distance



