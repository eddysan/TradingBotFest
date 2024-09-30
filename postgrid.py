from functions import *
#import numpy as np
#import json
#from binance.client import Client
#import requests


data_grid = load_config('config.json')

# Set up authentication
binance_config_file = load_config('../credentials.json')  
api_key = binance_config_file['api_key']
api_secret = binance_config_file['api_secret']

client = Client(api_key, api_secret)

# get precition on decimals for token pair
data_grid['price_decimal'], data_grid['quantity_decimal'] = get_quantity_precision(client, data_grid)

# getting account balance
account_balance = get_account_balance(client)
sl_compound = round(float(account_balance) * 0.10, 2)

# try input and apply default values
data_grid['token_pair'] = input("Token Pair (BTCUSDT): ").upper() + "USDT"
data_grid['grid_side'] = str(input("Grid Side (long): ")).upper() or 'LONG'
data_grid['grid_distance'] = float(input("Grid Distance (2%): ") or 2) / 100
data_grid['token_increment'] = float(input("Token Increment (40%): ") or 40) / 100
data_grid['sl_amount'] = float(input("Stop Loss Amount " + "(" + str(sl_compound) + "USDT):") or sl_compound)
data_grid['entry_price'] = float(input("Entry Price: ") or 0.00000)

# if compound is activated is not neccesary entry token
if data_grid['sl_amount'] != sl_compound:    
    data_grid['entry_quantity'] = float(input("Entry Token: ") or 0)
else:
    data_grid['entry_quantity'] = round(sl_compound / data_grid['entry_price'], data_grid['quantity_decimal'])


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
#print(data_grid)
    

data_grid['entry_order'] = post_order(client, data_grid, 'entry_order')
#print(data_grid)

data_grid['body_order'] = post_order(client, data_grid,'body_order')
#print(data_grid)

