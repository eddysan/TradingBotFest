import json
from binance.client import Client
import time
import logging
import os
from packages import *

# logging config
os.makedirs('logs', exist_ok=True) # creates logs directory if doesn't exist

# Create a logger object
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Overall logger level

console_handler = logging.StreamHandler()  # Logs to console
console_handler.setLevel(logging.INFO)  # Only log INFO and above to console

file_handler = logging.FileHandler(f"logs/positions.log")  # Logs to file
file_handler.setLevel(logging.DEBUG)  # Log DEBUG and above to file

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s') # formatter
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

if logger.hasHandlers(): # Clear any previously added handlers (if needed)
    logger.handlers.clear()

logger.addHandler(console_handler)
logger.addHandler(file_handler)

# INPUT symbol 
symbol = input("Symbol [BTC]: ").upper() + "USDT"

# INPUT side (default to LONG)
side = input("Side [LONG|SHORT]: ").upper() or 'LONG'

operation_code = f"{symbol}-{side}" 

grid = LUGrid(operation_code)

grid.update_current_position() #read current position
grid.update_entry_line() # updating entry line from current_line values
logging.info(f"Generating GD from entry_line: {grid.data_grid['entry_line']}")
grid.clean_order('GD') # clean grid orders
grid.clean_order('TP') # clean take profit orders
grid.clean_order('SL') # clean stop loss order
grid.generate_grid() # generate new grid points
grid.post_grid_order() # generate new grid and post it, taking entry price as entry and post it
grid.post_sl_order() # post stop loss order
grid.post_tp_order() # post take profit order
grid.write_data_grid() # saving all configuration to json

