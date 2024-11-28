from datetime import datetime
import os
import uuid
import json
from binance.client import Client
import math
import logging
import time
from decimal import Decimal
from package_common import *


# input data from console
def input_data(config_file):
    logging.debug(f"INPUT DATA...")
    
    client = get_connection()  # Open Binance connection
            
    # INPUT symbol
    if config_file['symbol']['input']:   
        config_file['symbol']['value'] = input("Symbol (BTC): ").upper() + "USDT"

    # getting wallet current balance
    config_file['wallet']['usdt_balance'] = round(next((float(b['balance']) for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0), 2)
    config_file['compound']['quantity'] = round(float(config_file['wallet']['usdt_balance']) * config_file['compound']['risk'], 2)

    # Getting precisions for the symbol
    info = client.futures_exchange_info()['symbols']
    symbol_info = next((x for x in info if x['symbol'] == config_file['symbol']['value']), None)
    
    # Retrieve precision filter 
    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            config_file['step_size'] = float(f['stepSize'])
        elif f['filterType'] == 'PRICE_FILTER':
            config_file['tick_size'] = float(f['tickSize'])
    
    config_file['price_precision'] = symbol_info['pricePrecision']
    config_file['quantity_precision'] = symbol_info['quantityPrecision']

    # INPUT side (default to LONG)
    if config_file['side']['input']:
        config_file['side']['value'] = input("Side (LONG|SHORT): ").upper() or "LONG"

    # INPUT entry price
    if config_file['entry_price']['input']:
        tick_increment = int(abs(math.log10(config_file['tick_size'])))
        config_file['entry_price']['value'] = round(float(input("Entry Price ($): ")), tick_increment)

    # INPUT stop_loss_amount
    if config_file['stop_loss_amount']['input']:
        config_file['stop_loss_amount']['value'] = float(input(f"Stop Loss Amount ({config_file['compound']['quantity']}$): ") or config_file['compound']['quantity'])

    # INPUT quantity
    if config_file['entry_quantity']['input']: # if entry quantity is enabled
        entry_token = round(float(config_file['compound']['quantity']) / config_file['entry_price']['value'], config_file['quantity_precision']) # converting compound amount to tokens
        config_file['entry_quantity']['value'] = float(input(f"Entry Quantity ({entry_token} {config_file['symbol']['value'][:-4]}): ") or entry_token) # getting quantity in USDT

    # initialising entry line
    config_file['entry_line']["side"] = 'BUY' if config_file['side']['value'] == 'LONG' else 'SELL'
    config_file['entry_line']["position_side"] = config_file['side']['value']

    # filling take_profit_line
    config_file['take_profit_line']['side'] = 'SELL' if config_file['side']['value'] == 'LONG' else 'BUY' #if the operation is LONG then the TP should be SELL and viceversa
    config_file['take_profit_line']['position_side'] = config_file['side']['value'] #mandatory for hedge mode, LONG or SHORT
        
    # unload_line data
    config_file['unload_line']['side'] = 'SELL' if config_file['side']['value'] == 'LONG' else 'BUY' # limit order to unload plus quantity of tokens
    config_file['unload_line']['position_side'] = config_file['side']['value']
        
    # stop_loss_line filling data
    config_file['stop_loss_line']['side'] = 'SELL' if config_file['side']['value'] == 'LONG' else 'BUY' #if the operation is LONG then the SL should be SELL
    config_file['stop_loss_line']['position_side'] = config_file['side']['value']
        
    # Generate operation code
    operation_code = f"{config_file['symbol']['value']}_{config_file['side']['value']}"

    # writting to data grid
    write_config_data('ops', operation_code + ".json", config_file)
        
    return operation_code


class CardiacGrid:
    
    def __init__(self, operation_code):
        
        # getting operation code
        self.operation_code = operation_code # operation code
        self.data_grid = read_config_data(f"ops/{self.operation_code}.json") # reading config file
        
        # new connection to binance
        self.client = get_connection()
        
        
    @property
    def symbol(self):
        return self.data_grid['symbol']['value']
            
    # Write data grid to operations folder
    def write_data_grid(self):
        conf_file = f"{self.operation_code}.json"
        write_config_data("ops", conf_file, self.data_grid)
    
    # round price to increment accepted by binance
    def round_to_tick_size(self, price):
        tick_increment = int(abs(math.log10(self.data_grid['tick_size'])))
        return round(price, tick_increment)
    

    # update currento position from binance
    def update_current_position(self):
        
        logging.info(f"{self.operation_code} UPDATING CURRENT POSITION FROM BINANCE...")
        
        try:
            # Fetch futures position information
            response = self.client.futures_position_information(symbol=self.data_grid['symbol']['value'])
            
            self.data_grid['current_line']['active'] = False
            
            # Loop through the list to find the relevant position based on 'positionSide'
            for position_info in response:
                if float(position_info['positionAmt']) != 0:  # Skip empty positions if the exchange is in hedge mode the response 2 current position, one is 0
                    self.data_grid['current_line']['price'] = self.round_to_tick_size(float(position_info['entryPrice']))
                    self.data_grid['current_line']['quantity'] = round(abs(float(position_info['positionAmt'])), self.data_grid['quantity_precision'])
                    self.data_grid['current_line']['position_side'] = position_info['positionSide']
                    self.data_grid['current_line']['active'] = True
                    
                    logging.debug(f"{self.operation_code} Current position from Binance: {position_info}")
                    logging.debug(f"{self.operation_code} data_grid[current_line]: {self.data_grid['current_line']}")
                    logging.info(f"{self.operation_code} Current position updated: {self.data_grid['current_line']['price']} | {self.data_grid['current_line']['quantity']}")
        
        except Exception as e:
            # if there is no position
            logging.exception(f"{self.operation_code} There is no position information: {e}")

    # generate entry_line
    def generate_entry(self):
        self.data_grid['entry_line']['price'] = self.data_grid['entry_price']['value']
        self.data_grid['entry_line']['quantity'] = self.data_grid['entry_quantity']['value']
        self.data_grid['entry_line']["cost"] = round(self.data_grid['entry_line']["price"] * self.data_grid['entry_line']["quantity"], 2)

    
    # generate the entire grid points, stop loss and take profit
    def generate_stop_loss(self):
        logging.info(f"{self.operation_code} GENERATING STOP_LOSS DATA...")
        
        if self.data_grid['current_line']['price'] != 0 and self.data_grid['current_line']['quantity'] != 0: # as condition
        
            try:
                # set stop loss taking the first point, entry line
                self.data_grid['current_line']['distance'] = (self.data_grid['stop_loss_amount']['value'] * 100) / (self.data_grid['current_line']['price'] * self.data_grid['current_line']['quantity'])
        
                if self.data_grid['side']['value'] == 'LONG':
                    self.data_grid['stop_loss_line']['price'] = abs(self.round_to_tick_size( float(self.data_grid['current_line']['price'] - (self.data_grid['current_line']['price'] * self.data_grid['current_line']['distance'] / 100) )))
                    self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['current_line']['price'] - self.data_grid['stop_loss_line']['price']) / self.data_grid['current_line']['price'],4)
            
                if self.data_grid['side']['value'] == 'SHORT':
                    self.data_grid['stop_loss_line']['price'] = abs(self.round_to_tick_size(float(self.data_grid['current_line']['price'] + (self.data_grid['current_line']['price'] * self.data_grid['current_line']['distance'] / 100) )))
                    self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['stop_loss_line']['price'] - self.data_grid['current_line']['price']) / self.data_grid['current_line']['price'],4)

                self.data_grid['stop_loss_line']['quantity'] = self.data_grid['current_line']['quantity']
                        
                logging.debug(f"{self.operation_code} stop_loss_line generated: {self.data_grid['stop_loss_line']}")

            except Exception as e:
                self.data_grid['stop_loss_line']['price'] = 0
                self.data_grid['stop_loss_line']['quantity'] = 0
                self.data_grid['stop_loss_line']['status'] = 'EMPTY'
                logging.debug(f"{self.operation_code} Error generating stop loss data: {e}")
            
        else:
            logging.debug(f"{self.operation_code} Can't generate stop loss data because there is no current line: {self.data_grid['current_line']}")
    
    # generate take profit line
    def generate_take_profit(self):
        
        if self.data_grid['current_line']['price'] != 0 and self.data_grid['current_line']['quantity'] != 0:
        
            # Calculate the take profit price based on the side
            try:
                price_factor = 1 + self.data_grid['take_profit_line']['distance'] if self.data_grid['side']['value'] == 'LONG' else 1 - self.data_grid['take_profit_line']['distance']
                self.data_grid['take_profit_line']['price'] = self.round_to_tick_size(self.data_grid['current_line']['price'] * price_factor)
                self.data_grid['take_profit_line']['status'] = 'FILLED'
        
                logging.debug(f"{self.operation_code} take_profit_line generated: {self.data_grid['take_profit_line']}")

            except Exception as e:
                self.data_grid['take_profit_line']['status'] = 'EMPTY'
                logging.debug(f"{self.operation_code} Error generating take profit line: {e}")

        else:
            logging.debug(f"{self.operation_code} There is no data on current_line: {self.data_grid['current_line']}")
    

    # generate unload line
    def generate_unload(self):
        
        if self.data_grid['current_line']['price'] != 0 and self.data_grid['current_line']['quantity'] != 0: # requeriments
        
            # Calculate the unload price based on the side (LONG or SHORT)
            try:
                price_factor = 1 + self.data_grid['unload_line']['distance'] if self.data_grid['side']['value'] == 'LONG' else 1 - self.data_grid['unload_line']['distance']
                self.data_grid['unload_line']['price'] = self.round_to_tick_size(self.data_grid['current_line']['price'] * price_factor)
            
                # Calculate unload quantity
                self.data_grid['unload_line']['quantity'] = round(
                    self.data_grid['current_line']['quantity'] - self.data_grid['entry_line']['quantity'], # always take the original quantity inserted
                    self.data_grid['quantity_precision']
                    )

                logging.debug(f"{self.operation_code} unload_line to post: {self.data_grid['unload_line']}")

            except Exception as e:
                logging.debug(f"{self.operation_code} Error generating unload line")

        else:
            logging.debug(f"{self.operation_code} Can't generate unload line because current_line data: {self.data_grid['current_line']}")



    # post entry order
    def post_entry_order(self):

        logging.debug(f"{self.operation_code} POSTING ENTRY ORDER TO BINANCE...")

        if self.data_grid['entry_line']['price'] != 0 and self.data_grid['entry_line']['quantity'] != 0:
    
            try:
                # Create the entry order
                response = self.client.futures_create_order(
                    symbol = self.data_grid['symbol']['value'],
                    side = self.data_grid['entry_line']['side'],
                    type = 'LIMIT',
                    timeInForce = 'GTC',
                    positionSide = self.data_grid['entry_line']['position_side'],
                    price = self.data_grid['entry_line']['price'],
                    quantity = self.data_grid['entry_line']['quantity'],
                    newClientOrderId = f"CARIN_0_{self.operation_code}_{str(uuid.uuid4())[:5]}"
                    )

                # Update entry_line with order response data
                self.data_grid['entry_line']['order_id'] = response['orderId']
                self.data_grid['entry_line']['status'] = response['status']
                self.data_grid['entry_line']['client_order_id'] = response['clientOrderId']
            
                # Log the placed order details
                logging.debug(f"{self.operation_code} entry_line posted to binance: {self.data_grid['entry_line']}")
                logging.debug(f"{self.operation_code} Binance response: {response}")
                logging.info(f"{self.operation_code} ✅ {self.data_grid['entry_line']['entry']} | {self.data_grid['entry_line']['price']} | {self.data_grid['entry_line']['quantity']} | {self.data_grid['entry_line']['cost']} ")

            except Exception as e:
                logging.exception(f"{self.operation_code} Error placing entry_line order: {self.data_grid['entry_line']} \n {e}")
                logging.info(f"{self.data_grid['symbol']['value']} Error placing entry_line order: {e}")

        else:
            logging.debug(f"{self.operation_code} Can't generate entry order because there is no data: {self.data_grid['entry_line']}")

    
    # post entry order
    def post_stop_loss_order(self):
        logging.debug(f"{self.operation_code} POSTING STOP_LOSS ORDER...")
        
        if self.data_grid['stop_loss_line']['price'] != 0: # is status is empty, then there is no data to post in stop loss order
        
            try:
                # Post the stop loss order
                response = self.client.futures_create_order(
                    symbol = self.data_grid['symbol']['value'],
                    side = self.data_grid['stop_loss_line']['side'],  # SL for LONG is SELL and vice versa
                    positionSide = self.data_grid['stop_loss_line']['position_side'],
                    type = 'STOP_MARKET',
                    stopPrice = "{:0.0{}f}".format(self.data_grid['stop_loss_line']['price'], self.data_grid['price_precision']),
                    closePosition = True,
                    newClientOrderId = f"CARSL_0_{self.operation_code}_{str(uuid.uuid4())[:5]}"
                    )

                # Update stop loss line with response data
                self.data_grid['stop_loss_line']['order_id'] = response['orderId']
                self.data_grid['stop_loss_line']['status'] = response['status']
                self.data_grid['stop_loss_line']['client_order_id'] = response['clientOrderId']
            
                # Log the placed order details
                logging.debug(f"{self.operation_code} stop_loss_line posted to binance: {self.data_grid['stop_loss_line']}")
                logging.debug(f"{self.operation_code} stop_loss_line binance response: {response}")
            
                # Log successful stop loss order
                logging.info(f"{self.operation_code} ✅ {self.data_grid['stop_loss_line']['entry']} ({round(self.data_grid['stop_loss_line']['distance']*100, 2)}%) | "
                             f"{self.data_grid['stop_loss_line']['price']} | {self.data_grid['stop_loss_line']['quantity']} | "
                             f"{self.data_grid['stop_loss_line']['cost']}")

            except Exception as e:
                logging.exception(f"{self.operation_code} Error placing stop loss order: {e}")

        else:
            logging.debug(f"{self.operation_code} Can't post stop loss because of data: {self.data_grid['stop_loss_line']}")

    # post take profit order
    def post_take_profit_order(self):
        logging.debug(f"{self.operation_code} POSTING TAKE PROFIT ORDER TO BINANCE...")

        if self.data_grid['take_profit_line']['price'] != 0:
        
            try:
                # Post the take profit order
                response = self.client.futures_create_order(
                    symbol = self.data_grid['symbol']['value'],
                    side = self.data_grid['take_profit_line']['side'],  # TP for LONG is SELL and vice versa
                    positionSide = self.data_grid['take_profit_line']['position_side'],
                    type = 'TAKE_PROFIT_MARKET',
                    stopPrice = self.data_grid['take_profit_line']['price'],
                    closePosition = True,
                    newClientOrderId = f"CARTP_0_{self.operation_code}_{str(uuid.uuid4())[:5]}"
                    )

                # Update take profit line with response data
                self.data_grid['take_profit_line']['order_id'] = response['orderId']
                self.data_grid['take_profit_line']['status'] = response['status']
                self.data_grid['take_profit_line']['client_order_id'] = response['clientOrderId']
                
                # Log the placed order details
                logging.debug(f"{self.operation_code} take_profit_line posted to binance: {self.data_grid['take_profit_line']}")
                logging.debug(f"{self.operation_code} take_profit_line binance response: {response}")
            
                # Log the successful order
                logging.info(f"{self.operation_code} ✅ {self.data_grid['take_profit_line']['entry']} ({round(self.data_grid['take_profit_line']['distance']*100,2)}%) | "
                             f"{self.data_grid['take_profit_line']['price']} | {self.data_grid['take_profit_line']['quantity']} | "
                             f"{self.data_grid['take_profit_line']['cost']}")
            
            except Exception as e:
                logging.exception(f"{self.operation_code} Error placing take profit order: {e}")

        else:
            logging.debug(f"{self.operation_code} Can't post take_profit because of data: {self.data_grid['take_profit_line']}")
            
    
    # post unload order
    def post_unload_order(self):
        logging.debug(f"{self.operation_code} POSTING UNLOAD ORDER...")
        
        if self.data_grid['unload_line']['quantity'] != 0 and self.data_grid['unload_line']['price'] != 0: # for first entry
        
            try:

                # Post the limit order
                response = self.client.futures_create_order(
                    symbol = self.data_grid['symbol']['value'],
                    side = self.data_grid['unload_line']['side'],
                    type = 'LIMIT',
                    timeInForce = 'GTC',
                    positionSide = self.data_grid['unload_line']['position_side'],
                    price = self.data_grid['unload_line']['price'],
                    quantity = self.data_grid['unload_line']['quantity'],
                    newClientOrderId = f"CARUL_0_{self.operation_code}_{str(uuid.uuid4())[:5]}"
                    )

                # Update unload line with the response data
                self.data_grid['unload_line']['order_id'] = response['orderId']
                self.data_grid['unload_line']['status'] = response['status']
                self.data_grid['unload_line']['client_order_id'] = response['clientOrderId']

                logging.debug(f"{self.operation_code} unload_line response from binance: {response}")
            
                # Log the success message
                logging.info(f"{self.operation_code} ✅ {self.data_grid['unload_line']['entry']} | "
                             f"{self.data_grid['unload_line']['price']} | {self.data_grid['unload_line']['quantity']}")
        
            except KeyError as e:
                logging.exception(f"{self.operation_code} Missing key in order data: {e}")
            except Exception as e:
                logging.exception(f"{self.operation_code} Error posting order: {e}")

        else:
            logging.debug(f"{self.operation_code} Can't post unload order because of data: {self.data_grid['unload_line']}")


    # Write data grid to operations folder
    def write_data_grid(self):
        logging.debug(f"{self.operation_code} WRITTING DATA_GRID FILE...")
        
        write_config_data('ops', f"{self.operation_code}.json", self.data_grid)

