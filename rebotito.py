import json
from binance.client import Client
import time
from model import *

# input data from terminal and save to operations folder
#operation_code = input_data()

#operation_code = '2410071736ADAUSDTLONG' # test


#grid = LUGrid(operation_code)
#grid.post_entry_order()
#grid.post_grid_order()
#grid.post_sl_order()
#grid.post_tp_order()
#grid.write_data_grid()


operation_code = '10091015-C98-L' # test
grid = LUGrid(operation_code)
grid.clean_grid_order()
grid.clean_sl_order()
grid.clean_tp_order()
grid.clean_ul_order()


