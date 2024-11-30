

from binance.client import Client
import json
import logging
import os

from cleanORDERS import position_side
from package_common import *

def input_data(config_file):
    logging.debug(f"INPUT DATA")

    config_long = config_file
    config_short = config_file

    # INPUT symbol
    if config_file['symbol']['input']:
        symbol = input(f"Symbol RZ(BTC): ").upper() + 'USDT'
        config_file['symbol']['value'] = symbol
        config_long['symbol']['value'] = symbol
        config_short['symbol']['value'] = symbol

    client = get_connection() #open connection
    response = client.futures_position_information(symbol=config_file['symbol']['value']) #fetch current position information

    # Loop through the list to find the relevant position
    for position_info in response:
        if position_info['positionSide'] == 'LONG' and position_info['positionAmt'] != 0:  # Checking if there is a position
            print(
                f"{position_info['symbol']}_{position_info['positionSide']} Taking current position as entry values... \n "
                f"Position side: {position_info['positionSide']} \n"
                f"Entry Price: {position_info['entryPrice']} \n "
                f"Entry Quantity: {position_info['positionAmt']}")

            config_long['entry_line']['position_side'] = position_info['positionSide']
            config_long['entry_line']['price'] = float(position_info['entryPrice'])
            config_long['entry_line']['quantity'] = float(position_info['positionAmt'])
            config_short['entry_line']['price'] = float(round_to_tick(input(f"Hedge price ($): "), config_long['tick_size'])) # getting short prices
            config_long['position_side']['value'] = 'LONG'
            config_short['position_side']['value'] = 'LONG'
            config_file['position_side']['input'] = False
            config_long['entry_line']['enabled'] = False
            config_short['entry_line']['enabled'] = False

        if position_info['positionSide'] == 'SHORT' and position_info['symbol']['value'] != 0:
            print(
                f"{position_info['symbol']}_{position_info['positionSide']} Taking current position as entry values... \n "
                f"Position side: {position_info['positionSide']} \n"
                f"Entry Price: {position_info['entryPrice']} \n "
                f"Entry Quantity: {position_info['positionAmt']}")
            config_short['entry_line']['position_side'] = position_info['positionSide']
            config_short['entry_line']['price'] = float(position_info['entryPrice'])
            config_short['entry_line']['quantity'] = float(position_info['positionAmt'])
            config_long['entry_line']['price'] = float(round_to_tick(input(f"Hedge price ($): "), config_long['tick_size'])) #getting hedge price
            config_long['position_side']['value'] = 'SHORT'
            config_short['position_side']['value'] = 'SHORT'
            config_file['position_side']['input'] = False
            config_short['entry_line']['enabled'] = False
            config_long['entry_line']['enabled'] = False

    # getting wallet current balance
    wallet_balance_usdt = round(next((float(b['balance']) for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0), 2)
    config_long['wallet_balance_usdt'] = wallet_balance_usdt
    config_short['wallet_balance_usdt'] = wallet_balance_usdt

    # Getting precisions for the symbol
    info = client.futures_exchange_info()['symbols']
    symbol_info = next((x for x in info if x['symbol'] == config_file['symbol']['value']), None)

    # Retrieve precision filter
    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            config_long['step_size'] = float(f['stepSize'])
            config_short['step_size'] = float(f['stepSize'])
        elif f['filterType'] == 'PRICE_FILTER':
            config_long['tick_size'] = float(f['tickSize'])
            config_short['tick_size'] = float(f['tickSize'])

    config_long['price_precision'] = symbol_info['pricePrecision']
    config_short['price_precision'] = symbol_info['pricePrecision']
    config_long['quantity_precision'] = symbol_info['quantityPrecision']
    config_short['quantity_precision'] = symbol_info['quantityPrecision']

    # INPUT position side
    if config_file['position_side']['input']:
        position_side = input(f"Position side (LONG|SHORT): ").upper() or "LONG"
        config_long['position_side']['value'] = position_side
        config_short['position_side']['value'] = position_side

    # INPUT price for long and short
    if config_long['entry_line']['enabled'] == True and config_long['position_side']['value'] == 'LONG': # if the position side is LONG then hedge point is short
        config_long['entry_line']['price'] = float(round_to_tick(input(f"Entry price ($): "), config_long['tick_size']))
        config_short['entry_line']['price'] = float(round_to_tick(input(f"Hedge price ($): "), config_long['tick_size']))

    if config_short['entry_line']['enabled'] == True and config_short['position_side']['value'] == 'SHORT': # if position side is SHORT then hedge point is long
        config_short['entry_line']['price'] = float(round_to_tick(input(f"Entry price ($): "), config_long['tick_size']))
        config_long['entry_line']['price'] = float(round_to_tick(input(f"Hedge price ($): "), config_long['tick_size']))

    # INPUT quantity
    if config_long['entry_line']['enabled'] == True and config_long['position_side']['value'] == 'LONG':
        hedge_distance = get_distance(config_long['entry_line']['price'], config_short['entry_line']['price'],'SHORT')
        suggested_quantity = (config_long['wallet_balance_usdt'] * config_long['risk']) / hedge_distance
        usdt_quantity = input(f"Entry quantity ({suggested_quantity}$): ")
        config_long['entry_line']['quantity'] = round(usdt_quantity / config_long['entry_line']['price'], config_long['entry_line']['quantity_precision'])

    if config_short['entry_line']['enabled'] == True and config_short['position_side']['value'] == 'SHORT':
        hedge_distance = get_distance(config_short['entry_line']['price'], config_long['entry_line']['price'],'LONG')
        suggested_quantity = (config_short['wallet_balance_usdt'] * config_short['risk']) / hedge_distance
        usdt_quantity = input(f"Entry quantity ({suggested_quantity}$): ")
        config_short['entry_line']['quantity'] = round(usdt_quantity / config_long['entry_line']['price']. config_short['entry_line']['quanity_precision'])

    operation_code = f"{config_file['symbol']['value']}_{config_file['position_side']['value']}"

    return operation_code


