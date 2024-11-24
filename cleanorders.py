#!/usr/bin/env python3

import os
import sys
import json
from binance.client import Client
import time
import logging
#from tlu_cardiac_pack import *
from tlu_pack import *
#from clean_pack import *

# Activating the virtual environment
venv_path = os.path.join(os.path.dirname(__file__), '.venv/bin/activate_this.py')
if os.path.exists(venv_path):
    with open(venv_path) as f:
        exec(f.read(), {'__file__': venv_path})

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
symbol = input("Symbol (BTC): ").upper() + "USDT"

# INPUT side (default to LONG)
side = input("Side to clean: (LONG|SHORT|ALL): ").upper() or 'ALL'

#client = get_connection()

if side != 'ALL':
    operation_code = f"{symbol}_{side}"
    grid = LUGrid(operation_code)
    grid.clean_order('IN') # clean entry order
    grid.clean_order('GD') # clean grid orders
    grid.clean_order('TP') # clean take profit orders
    grid.clean_order('SL') # clean stop loss order
    grid.clean_order('HD') # clean hedge order
    grid.write_data_grid()

if side == 'ALL':
    operation_code = f"{symbol}_LONG"
    grid = LUGrid(operation_code)
    grid.clean_open_orders()
    grid.write_data_grid()
        
