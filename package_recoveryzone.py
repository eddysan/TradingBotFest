from binance.client import Client
import json
import logging
import os

from package_common import *



def input_data():
    logging.debug(f"INPUT DATA")

    config = read_config_data("config/recoveryzone.config") #reading default config file
    config['product_factor'] = round((config['target_factor'] + 1) / config['target_factor'], 2) # generating product factor

    # INPUT symbol
    config['symbol'] = input(f"Symbol (BTC): ").upper() + 'USDT' #getting symbol

    client = get_connection() #open connection

    # Getting precisions for the symbol
    info = client.futures_exchange_info()['symbols']
    symbol_info = next((x for x in info if x['symbol'] == config['symbol']), None)

    # Retrieve precision filter
    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            config['step_size'] = float(f['stepSize'])
        elif f['filterType'] == 'PRICE_FILTER':
            config['tick_size'] = float(f['tickSize'])

    config['price_precision'] = symbol_info['pricePrecision']
    config['quantity_precision'] = symbol_info['quantityPrecision']

    response = client.futures_position_information(symbol=config['symbol'])  # fetch current position information

    # Loop through the list to find filled positions
    for position_info in response:
        if float(position_info['positionAmt']) != 0:  # Checking if there is a position
            if position_info['positionSide'] == 'LONG': # check if the position is LONG
                print(
                    f"{position_info['symbol']}_{position_info['positionSide']} Taking current position as entry values... \n"
                    f"Position side: {position_info['positionSide']} \n"
                    f"Entry Price: {position_info['entryPrice']} \n"
                    f"Entry Quantity: {position_info['positionAmt']}")

                config['long']['entry_line']['position_side'] = position_info['positionSide']
                config['long']['entry_line']['price'] = float(position_info['entryPrice'])
                config['long']['entry_line']['quantity'] = abs(float(position_info['positionAmt']))
                config['long']['entry_line']['status'] = 'FILLED'
                config['position_side'] = 'LONG'

            if position_info['positionSide'] == 'SHORT':
                print(
                    f"{position_info['symbol']}_{position_info['positionSide']} Taking current position as entry values... \n"
                    f"Position side: {position_info['positionSide']} \n"
                    f"Entry Price: {position_info['entryPrice']} \n"
                    f"Entry Quantity: {abs(float(position_info['positionAmt']))}")
                config['short']['entry_line']['position_side'] = position_info['positionSide']
                config['short']['entry_line']['price'] = float(position_info['entryPrice'])
                config['short']['entry_line']['quantity'] = abs(float(position_info['positionAmt']))
                config['short']['entry_line']['status'] = 'FILLED'
                config['position_side'] = 'SHORT'

    # getting wallet current balance
    config['wallet_balance_usdt'] = round(next((float(b['balance']) for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0), 2)

    # INPUT position side
    if config['position_side'] == 'NONE':
        config['position_side'] = input(f"Position side (LONG|SHORT): ").upper() or "LONG"

    # INPUT price and quantity for long and short
    if  config['position_side'] == 'LONG': # if the position side is LONG then hedge point is short
        if config['long']['entry_line']['status'] == 'FILLED': # there is a current position then entry values for short as hedge
            config['short']['entry_line']['price'] = round_to_tick(float(input(f"Hedge SHORT price ($): ")), config['tick_size']) # entry price fot its hedge position
            config['short']['entry_line']['quantity'] = round(config['product_factor'] * config['long']['entry_line']['quantity'], config['quantity_precision'])
            config['short']['entry_line']['type'] = 'STOP_MARKET'

        if config['long']['entry_line']['status'] != 'FILLED': # there is no current position, we should filled from scratch
            config['long']['entry_line']['price'] = round_to_tick(float(input(f"Entry LONG price ($): ")), config['tick_size'])  # entry price for long position
            config['short']['entry_line']['price'] = round_to_tick(float(input(f"Hedge SHORT price ($): ")), config['tick_size'])  # entry price for long position
            config['long']['entry_line']['distance'] = get_distance(config['long']['entry_line']['price'],config['short']['entry_line']['price'],'SHORT')  # getting distance between prices
            suggested_quantity = round((config['wallet_balance_usdt'] * config['risk']) / config['long']['entry_line']['distance'], 2)  # getting the 1% or more of wallet
            # INPUT quantity
            usdt_quantity = float(input(f"Entry LONG quantity ({suggested_quantity}$): ") or suggested_quantity)
            config['long']['entry_line']['quantity'] = round(usdt_quantity / config['long']['entry_line']['price'],config['quantity_precision']) #quantity converted to coins
            config['short']['entry_line']['quantity'] = round(config['product_factor'] * config['long']['entry_line']['quantity'], config['quantity_precision']) #short quantity applied by product factor
            config['long']['entry_line']['type'] = 'LIMIT' # for entry line
            config['short']['entry_line']['type'] = 'STOP_MARKET' # for hedge line

    if config['position_side'] == 'SHORT': # if position side is SHORT then hedge point is long
        if config['short']['entry_line']['status'] == 'FILLED':
            config['long']['entry_line']['price'] = round_to_tick(float(input(f"Hedge LONG price ($): ")),config['tick_size'])
            config['long']['entry_line']['quantity'] = round(config['product_factor'] * config['short']['entry_line']['quantity'],config['quantity_precision'])  # quantity of hedge according of product factor
            config['long']['entry_line']['type'] = 'STOP_MARKET'

        if config['short']['entry_line']['status'] != 'FILLED':
            config['short']['entry_line']['price'] = round_to_tick(float(input(f"Entry SHORT price ($): ")), config['tick_size'])
            config['long']['entry_line']['price'] = round_to_tick(float(input(f"Hedge LONG price ($): ")), config['tick_size'])
            config['short']['entry_line']['distance'] = get_distance(config['short']['entry_line']['price'],config['long']['entry_line']['price'], 'LONG') #getting distance between prices
            suggested_quantity = round((config['wallet_balance_usdt'] * config['risk']) / config['short']['entry_line']['distance'], 2) # getting % of risk of wallet
            # INPUT quantity
            usdt_quantity = float(input(f"Entry SHORT quantity ({suggested_quantity}$): ") or suggested_quantity)
            config['short']['entry_line']['quantity'] = round(usdt_quantity / config['short']['entry_line']['price'], config['quantity_precision']) #convert USDT to tokens
            config['long']['entry_line']['quantity'] = round(config['product_factor'] * config['short']['entry_line']['quantity'], config['quantity_precision']) # quantity of hedge according of product factor
            config['short']['entry_line']['type'] = 'LIMIT' # short whould be limit
            config['long']['entry_line']['type'] = 'STOP_MARKET' #long should be hedge

    write_config_data('ops',f"{config['symbol']}.json",config)

    return config['symbol']


class RecoveryZone:

    def __init__(self, symbol):
        # getting operation code
        self.symbol = symbol
        self.data_grid = read_config_data(f"ops/{self.symbol}.json")  # reading config file
        self.position_side = self.data_grid['position_side']

        # new connection to binance
        self.client = get_connection()

    # post limit order
    def post_limit_order(self, data_grid):
        try:
            # Create the entry order
            response = self.client.futures_create_order(
                symbol=self.symbol,
                side=data_grid['side'],
                type=data_grid['type'],
                timeInForce='GTC',
                positionSide=data_grid['position_side'],
                price=data_grid['price'],
                quantity=data_grid['quantity']
            )

            # Log the placed order details
            logging.debug(
                f"{self.symbol}_{self.position_side} Binance response: {response}")
            logging.info(
                f"{self.symbol}_{self.position_side} - {data_grid['type']} | {data_grid['price']} | {data_grid['quantity']}... POSTED")

        except Exception as e:
            logging.exception(
                f"{self.symbol}_{self.position_side} Error placing order: {e}")

    # post hedge order
    def post_hedge_order(self, data_grid):
        try:
            # Create the entry order
            response = self.client.futures_create_order(
                symbol=self.symbol,
                side=data_grid['side'],
                type=data_grid['type'],
                timeInForce='GTC',
                positionSide=data_grid['position_side'],
                stopPrice=data_grid['price'],
                quantity=data_grid['quantity'],
                closePosition=False
            )

            # Log the placed order details
            logging.debug(
                f"{self.symbol}_{self.position_side} Binance response: {response}")
            logging.info(
                f"{self.symbol}_{self.position_side} - {data_grid['type']} | {data_grid['price']} | {data_grid['quantity']}... POSTED")

        except Exception as e:
            logging.exception(
                f"{self.symbol}_{self.position_side} Error placing order: {e}")

    # post both orders, limit and hedge
    def post_orders(self):

        if self.data_grid['long']['entry_line']['status'] != 'FILLED':
            if self.data_grid['long']['entry_line']['type'] == 'LIMIT': # limit order
                self.post_limit_order(self.data_grid['long']['entry_line'])

            if self.data_grid['long']['entry_line']['type'] == 'STOP_MARKET': #hedge order
                self.post_hedge_order(self.data_grid['long']['entry_line'])

            self.data_grid['long']['entry_line']['status'] = 'NEW'

        if self.data_grid['short']['entry_line']['status'] != 'FILLED':
            if self.data_grid['short']['entry_line']['type'] == 'LIMIT':
                self.post_limit_order(self.data_grid['short']['entry_line'])

            if self.data_grid['short']['entry_line']['type'] == 'STOP_MARKET':
                self.post_hedge_order(self.data_grid['short']['entry_line'])

            self.data_grid['short']['entry_line']['status'] = 'NEW'


    def update_current_position(self):
        response = self.client.futures_position_information(symbol=self.symbol)  # fetch current position information
        # Loop through the list to find the relevant position
        for position_info in response:
            if float(position_info['positionAmt']) != 0:  # Checking if there is a position
                if position_info['positionSide'] == 'LONG':
                    self.data_grid['long']['entry_line']['position_side'] = position_info['positionSide']
                    self.data_grid['long']['entry_line']['price'] = float(position_info['entryPrice'])
                    self.data_grid['long']['entry_line']['quantity'] = abs(float(position_info['positionAmt']))
                    self.data_grid['long']['entry_line']['status'] = 'FILLED'

                if position_info['positionSide'] == 'SHORT':
                    self.data_grid['short']['entry_line']['position_side'] = position_info['positionSide']
                    self.data_grid['short']['entry_line']['price'] = float(position_info['entryPrice'])
                    self.data_grid['short']['entry_line']['quantity'] = abs(float(position_info['positionAmt']))
                    self.data_grid['short']['entry_line']['status'] = 'FILLED'

    # operate
    def operate(self, message):
        self.symbol = message['o']['s']  # symbol
        self.position_side = message['o']['ps']  # position side like LONG or SHORT
        self.data_grid = read_config_data(f"ops/{self.symbol}.json")  # reading config file

        if message['o']['ot'] == 'LIMIT': # the operation is LIMIT generally, first operation
            logging.info(f"{self.symbol}_{self.position_side} Position is open")

        if message['o']['ot'] == 'STOP_MARKET' and message['o']['cp'] == False: # hedge order taken and close position is false
            self.data_grid['risk'] = round(self.data_grid['risk'] * self.data_grid['product_factor'], 2) # incresing risk
            self.update_current_position() # updating position before operate
            if message['o']['ps'] == 'LONG':
                if self.data_grid['risk'] > self.data_grid['max_risk']: #if risk is more than max then both operations should be same
                    new_quantity = self.data_grid['long']['entry_line']['quantity'] - self.data_grid['short']['entry_line']['quantity']
                    self.data_grid['short']['entry_line']['quantity'] = round(new_quantity, self.data_grid['quantity_precision']) #same amount
                    self.post_hedge_order(self.data_grid['short']['entry_line'])
                else:
                    new_quantity = (self.data_grid['product_factor'] * self.data_grid['long']['entry_line']['quantity']) - self.data_grid['short']['entry_line']['quantity']
                    self.data_grid['short']['entry_line']['quantity'] = round(new_quantity,self.data_grid['quantity_precision'])
                    self.post_hedge_order(self.data_grid['short']['entry_line'])



                # [ok] post another hedge recharged
                # calculate break even and post it
                # post take profit for current side short
                # post stop loss for oposite side long

            if message['o']['ps'] == 'SHORT': #order taken is in short position, then I should prepare hedge order for long position
                new_quantity = (self.data_grid['product_factor'] * self.data_grid['short']['entry_line']['quantity']) - self.data_grid['long']['entry_line']['quantity']
                self.data_grid['long']['entry_line']['quantity'] = round(new_quantity, self.data_grid['quantity_precision']) # quantity of hedge according of product factor
                self.post_hedge_order(self.data_grid['long']['entry_line'])

        if message['o']['ot'] == 'TAKE_PROFIT_MARKET' and message['o']['cp'] == True: # take profit and close position
            print("clean all")
            # clean all













