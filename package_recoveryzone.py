

from binance.client import Client
import json
import logging
import os
from package_common import *

def input_data(config_file):
    logging.debug(f"INPUT DATA")
    client = get_connection()

    # INPUT symbol
    if config_file['symbol']['input']:
        config_file['symbol']['value'] = input(f"Symbol (BTC): ").upper() + 'USDT'

    # INPUT position side
    if config_file['position_side']['input']:
        config_file['position_side']['value'] = input(f"Position side (LONG):").upper() or "LONG"

    # Fetch current position information
    response = client.futures_position_information(symbol=config_file['symbol']['value'])

    # Loop through the list to find the relevant position based on 'positionSide'
    for position_info in response:
        if position_info['positionSide'] == config_file['side']['value'] and float(
                position_info['positionAmt']) != 0:  # Cheking if there is a position
            print(
                f"{config_file['symbol']['value']}_{config_file['side']['value']} Taking current position as entry values. \n "
                f"Entry Price: {position_info['entryPrice']} \n "
                f"Entry Quantity: {position_info['positionAmt']})")
            config_file['entry_price']['value'] = float(position_info['entryPrice'])
            config_file['entry_quantity']['value'] = float(position_info['positionAmt'])
            # diabling input
            config_file['entry_price']['input'] = False
            config_file['entry_quantity']['input'] = False
            config_file['entry_line']['enabled'] = False
            break  # Exit after finding the first non-empty position






class Recovery:



