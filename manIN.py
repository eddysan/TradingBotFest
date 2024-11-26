import json
from binance.client import Client
import time
import logging
import os
from tlu_pack import *

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

operation_code = f"{symbol}_{side}"

grid = LUGrid(operation_code)

grid.update_current_position() # read position information at first the position will be same as entry_line
grid.update_entry_line() # because I don't type a entry line, we just need to read it        
logging.info(f"Generating TP from entry_line: {grid.data_grid['entry_line']}")
grid.post_tp_order() # when an entry line is taken, then take profit will be posted
grid.write_data_grid()

