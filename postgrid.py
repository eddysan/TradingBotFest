from functions import *
#import numpy as np
#import json
#from binance.client import Client
#import requests


data_grid = load_config('config.json')

# try input and apply default values
data_grid['token_pair'] = input("Token Pair (BTCUSDT): ").upper() + "USDT"
data_grid['grid_side'] = str(input("Grid Side (long): ")).upper() or 'LONG'
data_grid['grid_distance'] = float(input("Grid Distance (2%): ") or 2) / 100
data_grid['token_increment'] = float(input("Token Increment (40%): ") or 40) / 100
data_grid['sl_amount'] = float(input("Stop Loss Amount (10 USDT): ") or 10)

ep = str(input("Entry Price: ") or 0.00000)
data_grid['price_decimal'] = ep[::-1].find('.')
data_grid['entry_price'] = float(ep)

eq = str(input("Entry Token: ") or 0)
data_grid['quantity_decimal'] = eq[::-1].find('.')
data_grid['entry_quantity'] = float(eq)

# default variables to dev
#data_grid['token_pair'] = 'NEIROUSDT'
#data_grid['grid_side'] = 'LONG'
#data_grid['grid_distance'] = 0.02
#data_grid['token_increment'] = 0.40
#data_grid['sl_amount'] = 10.00
#data_grid['entry_price'] = 0.0011000
#data_grid['entry_quantity'] = 9090


# You can then proceed to use the generate function
data_grid = generate(data_grid)
print(data_grid)

data_grid['entry_order'] = post_order(data_grid, 'entry_order')
print(data_grid)

data_grid['body_order'] = post_order(data_grid,'body_order')
print(data_grid)

