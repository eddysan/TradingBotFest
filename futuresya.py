#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep 24 19:57:27 2024

@author: eddysan
"""
from binance.client import Client
import json

# load json config
def load_config(json_file):
  try:
    # Load the JSON file with default config
    with open(json_file, 'r') as file:
      data = json.load(file)
  except Exception as e:
    print(f"Error loading configuration: {e}")
  return data


binance_credentials = load_config('../credentials.json')

api_key = binance_credentials['api_key']
api_secret = binance_credentials['api_secret']
client = Client(api_key, api_secret)

symbol = 'ETHUSDT'
tar_profit = 0.09 #take profit when ROE hits 9%
lev = 20 #leverage

ticker_data = client.futures_symbol_ticker(symbol = symbol)
current_price = float(ticker_data["price"])
cp_adder = 1 + float(tar_profit / lev)
tp_price = round(current_price * cp_adder, 2)


res = client.futures_create_order(
        symbol = symbol,
        side = 'BUY',
        type = 'LIMIT',
        timeInForce = 'GTC',
        price = 2570.00,
        quantity = 0.008,
        positionSide = 'LONG'
        #isolated=True,
        #stopPrice=stop_price,
        #workingType='CONTRACT_PRICE' #or MARK PRICE
        )

print(res)
