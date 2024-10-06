#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# prompt messages  in order to get data externally
def get_external_data():    
    data_grid = {}

    # try input and apply default values
    data_grid['symbol'] = input("Token Pair (BTCUSDT): ").upper() + "USDT"
    data_grid['grid_side'] = str(input("Grid Side (long): ")).upper() or 'LONG'
    data_grid['grid_distance'] = float(input("Grid Distance (2%): ") or 2) / 100
    data_grid['quantity_increment'] = float(input("Token Increment (40%): ") or 40) / 100
    data_grid['sl_amount'] = float(input("Stop Loss Amount ($10): ") or 10.0)
    data_grid['entry_price'] = float(input("Entry Price: ") or 0.00000)
    data_grid['entry_quantity'] = float(input("Entry Quantity: ") or 0.00000)

    return data_grid

