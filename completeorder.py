import json
from binance.client import Client
import time
import logging
from packages import *

# logging config
os.makedirs('logs', exist_ok=True) # creates logs directory if doesn't exist

# Create a logger object
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Overall logger level

console_handler = logging.StreamHandler()  # Logs to console
console_handler.setLevel(logging.INFO)  # Only log INFO and above to console

file_handler = logging.FileHandler(f"logs/open_orders.log")  # Logs to file
file_handler.setLevel(logging.DEBUG)  # Log DEBUG and above to file

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s') # formatter
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

if logger.hasHandlers(): # Clear any previously added handlers (if needed)
    logger.handlers.clear()

logger.addHandler(console_handler)
logger.addHandler(file_handler)


# Reading default config file
config_file = read_config_data("config/config.json")

config_file['symbol']['input'] = True
config_file['side']['input'] = True
config_file['grid_distance']['input'] = True
config_file['quantity_increment']['input'] = True
config_file['stop_loss_amount']['input'] = True
config_file['entry_price']['input'] = False
config_file['entry_quantity']['input'] = False

# input data from terminal and save to operations folder
operation_code = input_data(config_file)

grid = LUGrid(operation_code)

grid.update_current_position() #read current position
grid.update_entry_line() # updating entry line from current_line values
grid.generate_grid() # generate new grid points
grid.post_grid_order() # generate new grid and post it, taking entry price as entry and post it
grid.post_sl_order() # post stop loss order
grid.post_tp_order() # post take profit order
grid.write_data_grid() # saving all configuration to json


