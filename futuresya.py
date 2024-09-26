#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep 24 19:57:27 2024

@author: eddysan
"""
from binance.client import Client

test_key = "uP1Hh54WChLGH0a81MqtNvxukonEhZWUUDyzebxtecsoiCIcy2AYHLfPYKrG8opF"
test_secret_key = "8JVTDWtYJhWfwDrrbY4Zh0T7xSCkMr2A7dkKvPjrWNPcuwj798UAuprGU7DomoST"
client = Client(test_key, test_secret_key)

symbol = 'ETHUSDT'
tar_profit = 0.09 #take profit when ROE hits 9%
lev = 20 #leverage

ticker_data = client.futures_symbol_ticker(symbol = symbol)
current_price = float(ticker_data["price"])
cp_adder = 1 + float(tar_profit / lev)
tp_price = round(current_price * cp_adder, 2)
qty = 0.2

client.futures_create_order(
        symbol = symbol,
        side = 'BUY',
        type = 'LIMIT',
        timeInForce = 'GTC',
        price = 2570.00,
        quantity = 0.008,
        #isolated=True,
        #stopPrice=stop_price,
        workingType='CONTRACT_PRICE' #or MARK PRICE
        )

