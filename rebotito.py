import json
from binance.client import Client
import time
from model import *

# input data from terminal and save to operations folder
operation_code = input_data()

#operation_code = '2410071736ADAUSDTLONG' # test

grid = LUGrid(operation_code)
grid.generate_grid()

grid.post_entry_order()
grid.post_grid_order()
grid.post_sl_order()
grid.post_tp_order()
grid.save_config()

