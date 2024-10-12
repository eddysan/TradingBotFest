import json
from binance.client import Client
import time
from packages import *

# input data from terminal and save to operations folder
operation_code = input_data()

# Basic logging configuration
logging.basicConfig(
    level=logging.NOTSET,  # Set to DEBUG to capture all levels of log messages
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/{operation_code}.log"),  # Logs to a file
        #adalogging.StreamHandler()  # Logs to the console
    ]
)

grid = LUGrid(operation_code)
grid.post_entry_order()
grid.generate_grid()
grid.post_grid_order()
grid.post_sl_order()
grid.post_tp_order()
grid.write_data_grid()

