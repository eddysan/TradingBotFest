import json
from binance.client import Client
import time
from packages import *

# input data from terminal and save to operations folder
#operation_code = input_data()
operation_code = 'PEOPLEUSDT-SHORT'

# Basic logging configuration
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to capture all levels of log messages
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/{operation_code}.log"),  # Logs to a file
        logging.StreamHandler()  # Logs to the console
    ]
)

grid = LUGrid(operation_code)
#grid.generate_grid()
#grid.post_entry_order()
#grid.post_grid_order()
#grid.post_sl_order()
#grid.post_tp_order()
#grid.write_data_grid()

#grid.update_current_position() #read current position
#grid.clean_ul_order()
#grid.post_ul_order()
#grid.post_tp_order() # post take profit order
#grid.write_data_grid() # saving all configuration to json

grid.update_current_position() #read current position
grid.update_entry_line() # updating entry line from current_line values
grid.clean_open_orders() # clean all open orders
grid.generate_grid() # generate new grid points
grid.post_grid_order() # generate new grid and post it, taking entry price as entry and post it
grid.post_sl_order() # post stop loss order
grid.post_tp_order() # post take profit order
grid.write_data_grid() # saving all configuration to json