import json
from binance.client import Client
#from binance.streams import BinanceSocketManager
#from websocket import WebSocketApp
import time
from model import *

# if compound is true then quantity will be taken as 10% of entire capital
data_grid = {"compound": False,
             "tp_distance": 0.05, #take profit at 5%
             "ul_distance": 0.005 #unload at 0.5%
    }


#data_grid = get_external_data(data_grid)

# default variables to dev
data_grid['symbol'] = 'ADAUSDT'
data_grid['grid_side'] = 'LONG'
data_grid['grid_distance'] = 0.02
data_grid['quantity_increment'] = 0.40
data_grid['sl_amount'] = 10
data_grid['entry_price'] = 0.345
data_grid['entry_quantity'] = 28

grid = LUGrid(data_grid)

grid.load_data(data_grid)
grid.generate_grid()
grid.generate_unload()

grid.post_entry_order()
grid.post_grid_order()
grid.post_sl_order()
grid.post_tp_order()
grid.print_grid()

