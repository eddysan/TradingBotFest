import json
from binance.client import Client
import time
from packages import *

# Reading default config file
config_file = read_data_grid("config.json")

# input data from terminal and save to operations folder
operation_code = input_data(config_file)

# Basic logging configuration
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to capture all levels of log messages
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/{operation_code}.log"),  # Logs to a file
        #logging.StreamHandler()  # Logs to the console
    ]
)

grid = LUGrid(operation_code)
grid.generate_grid()
grid.post_entry_order()
grid.post_grid_order()
grid.post_sl_order()
grid.post_tp_order()
grid.write_data_grid()

