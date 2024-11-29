from datetime import datetime
import os
import uuid
import json
from binance.client import Client
import math
import logging
import time
from package_common import *


# input data from console
def input_data(config_file):
    logging.debug(f"INPUT DATA...")
    
    client = get_connection()  # Open Binance connection
        
    # Helper to safely get user input with default fallback
    def get_input(prompt, default_value=None, cast_func=str):
        user_input = input(prompt).strip()
        return cast_func(user_input) if user_input else default_value
    
    # INPUT symbol
    if config_file['symbol']['input']:   
        config_file['symbol']['value'] = get_input("Symbol (BTC): ", "BTC").upper() + "USDT"

    # INPUT side (default to LONG)
    if config_file['side']['input']:
        config_file['side']['value'] = get_input("Side (LONG): ", "LONG", str).upper()

    # Fetch futures position information
    response = client.futures_position_information(symbol=config_file['symbol']['value'])

    # Loop through the list to find the relevant position based on 'positionSide'
    for position_info in response:
        if position_info['positionSide'] == config_file['side']['value'] and float(position_info['positionAmt']) != 0:  # Cheking if there is a position
            logging.info(f"{config_file['symbol']['value']}_{config_file['side']['value']} Taking current position as entry values. \n "
                         f"Entry Price: {position_info['entryPrice']} \n "
                         f"Entry Quantity: {position_info['positionAmt']})")
            config_file['entry_price']['value'] = position_info['entryPrice']
            config_file['entry_quantity']['value'] = position_info['positionAmt']
            #diabling input
            config_file['entry_price']['input'] = False
            config_file['entry_quantity']['input'] = False
            break  # Exit after finding the first non-empty position


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

    # INPUT entry price
    if config_file['entry_price']['input']:
        tick_increment = int(abs(math.log10(config_file['tick_size'])))
        config_file['entry_price']['value'] = round(get_input("Entry Price ($): ", 0.0, float), tick_increment)

    # INPUT grid distance
    if config_file['grid_distance']['input']:
        config_file['grid_distance']['value'] = get_input("Grid Distance (2%): ", 2, float) / 100 # default valur for grid distance is 2%

    # INPUT token increment
    if config_file['quantity_increment']['input']:
        config_file['quantity_increment']['value'] = get_input("Token Increment (40%): ", 40, float) / 100 # default increment is 40%

    # INPUT stop_loss_amount
    if config_file['stop_loss_amount']['input']:
        config_file['stop_loss_amount']['value'] = get_input(f"Stop Loss Amount ({config_file['compound']['quantity']}$): ", config_file['compound']['quantity'], float)
    
    # INPUT quantity
    if config_file['entry_quantity']['input']: # if entry quantity is enabled
        entry_q = round(get_input(f"Entry Quantity ({config_file['compound']['quantity']}$): ", config_file['compound']['quantity'], float), 2) # getting quantity in USDT
        config_file['entry_quantity']['value'] = round(entry_q / config_file['entry_price']['value'], config_file['quantity_precision']) #converting USDT entry to tokens
    
    # cleaning grid body    
    config_file['grid_body'] = []
    
    # initialising entry line
    config_file['entry_line']['price'] = config_file['entry_price']['value']
    config_file['entry_line']['quantity'] = config_file['entry_quantity']['value']
    config_file['entry_line']["side"] = 'BUY' if config_file['side']['value'] == 'LONG' else 'SELL'
    config_file['entry_line']["position_side"] = config_file['side']['value']
    config_file['entry_line']["cost"] = round(config_file['entry_line']["price"] * config_file['entry_line']["quantity"], 2)
                           
    # filling take_profit_line
    config_file['take_profit_line']['side'] = 'SELL' if config_file['side']['value'] == 'LONG' else 'BUY' #if the operation is LONG then the TP should be SELL and viceversa
    config_file['take_profit_line']['position_side'] = config_file['side']['value'] #mandatory for hedge mode, LONG or SHORT
        
    # unload_line data
    config_file['unload_line']['side'] = 'SELL' if config_file['side']['value'] == 'LONG' else 'BUY' # limit order to unload plus quantity of tokens
    config_file['unload_line']['position_side'] = config_file['side']['value']
        
    # stop_loss_line filling data
    config_file['stop_loss_line']['side'] = 'SELL' if config_file['side']['value'] == 'LONG' else 'BUY' #if the operation is LONG then the SL should be SELL
    config_file['stop_loss_line']['position_side'] = config_file['side']['value']
    
    # filling hedge line data
    config_file['hedge_line']['side'] = 'SELL' if config_file['side']['value'] == 'LONG' else 'BUY' #if the operation is LONG then the hedge should be SELL
    config_file['hedge_line']['position_side'] = config_file['side']['value']
    
    # Generate operation code
    operation_code = f"{config_file['symbol']['value']}_{config_file['side']['value']}"

    # saving to data grid
    write_config_data('ops', operation_code + ".json", config_file)
        
    return operation_code


# get transaction type
def get_transaction_type(message):
    # for grid
    if message['o']['ps'] == 'LONG' and message['o']['o'] == 'LIMIT' and message['o']['S'] == 'BUY':
        return 'GD'

    if message['o']['ps'] == 'SHORT' and message['o']['o'] == 'LIMIT' and message['o']['S'] == 'SELL':
        return 'GD'

    # for unload
    if message['o']['ps'] == 'LONG' and message['o']['o'] == 'LIMIT' and message['o']['S'] == 'SELL':
        return 'UL'

    if message['o']['ps'] == 'SHORT' and message['o']['o'] == 'LIMIT' and message['o']['S'] == 'BUY':
        return 'UL'

    # for take profit
    if message['o']['o'] == 'TAKE_PROFIT_MARKET':
        return 'TP'

    if message['o']['o'] == 'STOP_MARKET':
        return 'SL'



class LUGrid:
    
    def __init__(self, operation_code):
        
        # geetting operation code
        self.operation_code = operation_code # operation code
        
        self.data_grid = self.read_data_grid() # reading configuration file
        
        # new connection to binance
        self.client = get_connection()
        
        
    @property
    def symbol(self):
        return self.data_grid['symbol']['value']
    
    # read data grid in order to upload config
    def read_data_grid(self):
        logging.debug(f"{self.operation_code} READING DATA_GRID FILE...")
        operation_file = f"ops/{self.operation_code}.json"
        fallback_file = "config/config.json"  # The fallback file

        try:
            # Attempt to load the primary file
            if os.path.isfile(operation_file):
                with open(operation_file, 'r') as file:
                    config_file = json.load(file)
                    logging.debug(f"{self.operation_code} Successfully loaded: {operation_file}")
                    return config_file
            else:
                logging.warning(f"{self.operation_code} data_grid file '{operation_file}' not found. Attempting to load fallback config.json file.")

            # Attempt to load the fallback file if primary doesn't exist
            if os.path.isfile(fallback_file):
                with open(fallback_file, 'r') as file:
                    config_file = json.load(file)
                    logging.debug(f"{self.operation_code} Successfully loaded fallback file: {fallback_file}")
                    return config_file
            else:
                logging.error(f"{self.operation_code} Fallback config.json file '{fallback_file}' not found.")
                return None

        except json.JSONDecodeError as e:
            logging.error(f"{self.operation_code} JSONDecodeError in file: {operation_file if os.path.isfile(operation_file) else fallback_file} - {str(e)}")
            return None

        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            return None
        
        
    # Write data grid to operations folder
    def write_data_grid(self):
        logging.debug(f"{self.operation_code} WRITTING DATA_GRID FILE...")
        cfile = f"ops/{self.operation_code}.json"

        try:
            # Writing the JSON data to the file
            with open(cfile, 'w') as file:
                json.dump(self.data_grid, file, indent=4)
                logging.debug(f"{self.operation_code} Successfully saved data_grid to {cfile}.")

        except IOError as e:
            # Log the error with exception traceback
            logging.exception(f"{self.operation_code} Error writing file {self.operation_code}: {e}")
        except Exception as e:
            # Catch any other unexpected exceptions
            logging.exception(f"{self.operation_code} Unexpected error occurred while writing to {cfile}: {str(e)}")

    
    
    # round price to increment accepted by binance
    def round_to_tick_size(self, price):
        tick_increment = int(abs(math.log10(self.data_grid['tick_size'])))
        return round(price, tick_increment)
    
    
    # generate the entire grid points, stop loss and take profit
    def generate_grid(self):
        
        logging.debug(f"{self.operation_code} GENERATING DATA_GRID LINES...")
        
        # filling initial data to entry_line
        
        # current line is the pivot that store que current price in operation, this will change if the grid has chaged
        self.data_grid['current_line']['price'] = self.data_grid['entry_line']['price']
        self.data_grid['current_line']['quantity'] = self.data_grid['entry_line']['quantity']
        self.data_grid['current_line']['position_side'] = self.data_grid['entry_line']['position_side']
        
        # clean and initialize working variables
        self.data_grid['grid_body'] = [] #cleaning grid body before operations
        current_price = self.data_grid['entry_line']["price"]
        current_quantity = self.data_grid['entry_line']["quantity"]
        
        self.data_grid['average_line']['price'] = self.data_grid['entry_line']["price"]
        self.data_grid['average_line']['quantity'] = self.data_grid['entry_line']["quantity"]

        # set stop loss taking the first point, entry line
        self.data_grid['average_line']['sl_distance'] = (self.data_grid['stop_loss_amount']['value'] * 100) / (self.data_grid['average_line']['price'] *  self.data_grid['average_line']['quantity'])
        
        if self.data_grid['side']['value'] == 'LONG':
            self.data_grid['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid['average_line']['price'] - (self.data_grid['average_line']['price'] * self.data_grid['average_line']['sl_distance'] / 100) )
            self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['entry_line']['price'] - self.data_grid['stop_loss_line']['price']) / self.data_grid['entry_line']['price'],4)
            
        if self.data_grid['side']['value'] == 'SHORT':
                self.data_grid['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid['average_line']['price'] + (self.data_grid['average_line']['price'] * self.data_grid['average_line']['sl_distance'] / 100) )
                self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['stop_loss_line']['price'] - self.data_grid['entry_line']['price']) / self.data_grid['entry_line']['price'],4)

        self.data_grid['stop_loss_line']['quantity'] = self.data_grid['entry_line']['quantity']
        self.data_grid['stop_loss_line']['cost'] = self.data_grid['entry_line']['cost']

        while True:
            
            # increment as grid distance the price and quantity
            if self.data_grid['side']['value'] == 'LONG':
                new_price = current_price * (1 - self.data_grid['grid_distance']['value'])
            
            if self.data_grid['side']['value'] == 'SHORT':
                new_price = current_price * (1 + self.data_grid['grid_distance']['value'])
            
            new_quantity = current_quantity * (1 + self.data_grid['quantity_increment']['value'])
            
            # control if the new price is greater or lower than stop loss price, in order to stop generation of posts
            if self.data_grid['side']['value'] == 'LONG':
                if self.data_grid['stop_loss_line']['price'] > new_price:
                    break
                
            if self.data_grid['side']['value'] == 'SHORT':
                if new_price > self.data_grid['stop_loss_line']['price']:
                    break
            
            self.data_grid['grid_body'].append({"entry" : len(self.data_grid['grid_body'])+1,
                                   "side": 'BUY' if self.data_grid['side']['value'] == 'LONG' else 'SELL',
                                   "position_side": self.data_grid['side']['value'],
                                   "price" : self.round_to_tick_size(new_price), 
                                   "quantity" : round(new_quantity, self.data_grid['quantity_precision']), 
                                   "cost" : round(new_price * new_quantity, 2),
                                   })
            
            
            # calculate the average price and accumulated quantity if the position is taken
            self.data_grid['average_line']['price'] = self.round_to_tick_size( ((self.data_grid['average_line']['price'] * self.data_grid['average_line']['quantity']) + (new_price * new_quantity)) / (self.data_grid['average_line']['quantity'] + new_quantity)) 
            self.data_grid['average_line']['quantity'] = round(self.data_grid['average_line']['quantity'] + new_quantity, self.data_grid['quantity_precision'])
            
            self.data_grid['average_line']['sl_distance'] = (self.data_grid['stop_loss_amount']['value'] * 100) / (self.data_grid['average_line']['price'] *  self.data_grid['average_line']['quantity'])
            
            if self.data_grid['side']['value'] == 'LONG':
                self.data_grid['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid['average_line']['price'] - (self.data_grid['average_line']['price'] * self.data_grid['average_line']['sl_distance'] / 100) )
                self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['entry_line']['price'] - self.data_grid['stop_loss_line']['price']) / self.data_grid['entry_line']['price'],4)
            
            if self.data_grid['side']['value'] == 'SHORT':
                self.data_grid['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid['average_line']['price'] + (self.data_grid['average_line']['price'] * self.data_grid['average_line']['sl_distance'] / 100) )
                self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['stop_loss_line']['price'] - self.data_grid['entry_line']['price']) / self.data_grid['entry_line']['price'],4)

            self.data_grid['stop_loss_line']['quantity'] = round(self.data_grid['stop_loss_line']['quantity'] + new_quantity, self.data_grid['quantity_precision']) 
            self.data_grid['stop_loss_line']['cost'] = round(self.data_grid['stop_loss_line']['cost'] + (new_price * new_quantity), 2)
            
            current_price = new_price
            current_quantity = new_quantity
            
        logging.debug(f"{self.operation_code} grid_body generated: {self.data_grid['grid_body']}")
        logging.debug(f"{self.operation_code} stop_loss_line generated: {self.data_grid['stop_loss_line']}")
        
        self.data_grid['grid_size'] = len(self.data_grid['grid_body']) # saving length of grid
        
        # Calculate the take profit price based on the side
        price_factor = 1 + self.data_grid['take_profit_line']['distance'] if self.data_grid['side']['value'] == 'LONG' else 1 - self.data_grid['take_profit_line']['distance']
        self.data_grid['take_profit_line']['price'] = self.round_to_tick_size(self.data_grid['entry_line']['price'] * price_factor)
        logging.debug(f"{self.operation_code} take_profit_line generated: {self.data_grid['take_profit_line']}")
        
        # setting for hedge line if I need
        self.data_grid['hedge_line']['price'] = self.data_grid['stop_loss_line']['price']
        self.data_grid['hedge_line']['quantity'] = self.data_grid['stop_loss_line']['quantity']
        self.data_grid['hedge_line']['cost'] = self.data_grid['stop_loss_line']['cost']
        
        logging.debug(f"{self.operation_code} Grid generation completed")
        
        return None
    
            
    # update entry line data taking current line as data, and the current position will be the new entry
    def update_entry_line(self):
        logging.debug(f"{self.operation_code} UPDATING ENTRY_LINE FROM CURRENT_LINE...")
    
        # Update entry line with current line values
        self.data_grid['entry_line']['price'] = self.data_grid['current_line']['price']
        self.data_grid['entry_line']['quantity'] = self.data_grid['current_line']['quantity']
        self.data_grid['entry_line']['cost'] = round(self.data_grid['entry_line']['price'] * self.data_grid['entry_line']['quantity'], 2)
        
        logging.debug(f"{self.operation_code} current_line: {self.data_grid['current_line']}")
        logging.debug(f"{self.operation_code} entry_line updated: {self.data_grid['entry_line']}")
        
        return None
    
    
    # post entry order
    def post_entry_order(self):

        logging.debug(f"{self.operation_code} POSTING ENTRY ORDER TO BINANCE...")
        entry_line = self.data_grid.get('entry_line', {})
    
        try:
            # Create the entry order
            response = self.client.futures_create_order(
                symbol = self.data_grid['symbol']['value'],
                side = entry_line['side'],
                type = 'LIMIT',
                timeInForce = 'GTC',
                positionSide = entry_line['position_side'],
                price = entry_line['price'],
                quantity = entry_line['quantity'],
                newClientOrderId = f"{self.operation_code}_IN_0_{str(uuid.uuid4())[:5]}"
            )

            # Update entry_line with order response data
            entry_line['order_id'] = response.get('orderId', 0)
            entry_line['status'] = response.get('status', 'UNKNOWN')
            entry_line['client_order_id'] = response.get('clientOrderId', 'UNKNOWN')
            
            # Log the placed order details
            logging.debug(f"{self.operation_code} entry_line posted to binance: {entry_line}")
            logging.debug(f"{self.operation_code} Binance response: {response}")
            logging.info(f"{self.operation_code} ✅ {entry_line['entry']} | {entry_line['price']} | {entry_line['quantity']} | {entry_line['cost']} ")

        except Exception as e:
            logging.exception(f"{self.operation_code} Error placing entry_line order: {entry_line} \n {e}")
            logging.info(f"{self.data_grid['symbol']['value']} Error placing entry_line order: {e}")

        return None

            
    # post a limit order for grid body
    def post_grid_order(self):
        logging.debug(f"{self.operation_code} POSTING GRID_BODY TO BINANCE...")
        try:
            for i in range(len(self.data_grid['grid_body'])):
                response = self.client.futures_create_order(
                    symbol = self.data_grid['symbol']['value'],
                    side = self.data_grid['grid_body'][i]['side'],
                    type = 'LIMIT',
                    timeInForce = 'GTC',
                    positionSide = self.data_grid['grid_body'][i]['position_side'],
                    price = self.data_grid['grid_body'][i]['price'],  
                    quantity = self.data_grid['grid_body'][i]['quantity'],
                    newClientOrderId = f"{self.operation_code}_GD_{self.data_grid['grid_body'][i]['entry']}_{str(uuid.uuid4())[:5]}"
                    )
                self.data_grid['grid_body'][i]['order_id'] = response['orderId']
                self.data_grid['grid_body'][i]['status'] = response['status']
                self.data_grid['grid_body'][i]['client_order_id'] = response['clientOrderId']
                
                logging.debug(f"{self.operation_code} Posting grid line to binance: {self.data_grid['grid_body'][i]}")
                logging.debug(f"{self.operation_code} Binance response: {response}")
                logging.info(f"{self.operation_code} ✅ {self.data_grid['grid_body'][i]['entry']} | {self.data_grid['grid_body'][i]['price']} | {self.data_grid['grid_body'][i]['quantity']} | {self.data_grid['grid_body'][i]['cost']}")
                
        except KeyError as e:
            logging.exception(f"{self.operation_code} Posting grid orders: Missing key in order data: {e}")
        except Exception as e:
            logging.exception(f"Error posting grid data: {e}")
                
    # posting hedge order
    def post_hedge_order(self):
        logging.debug(f"{self.operation_code} POSTING HEDGE ORDER...")
        try:
            # Post the stop loss order
            response = self.client.futures_create_order(
                symbol = self.data_grid['symbol']['value'],
                side = self.data_grid['hedge_line']['side'],  # SL for LONG is SELL and vice versa
                positionSide = self.data_grid['hedge_line']['position_side'],
                type = 'STOP_MARKET',
                stopPrice = self.data_grid['hedge_line']['price'],
                quantity = self.data_grid['hedge_line']['quantity'],
                closePosition = False,
                newClientOrderId=f"{self.operation_code}_HD_0_{str(uuid.uuid4())[:5]}"
            )
            
            # upgrading hedge line
            self.data_grid['hedge_line']['order_id'] = response['orderId']
            self.data_grid['hedge_line']['status'] = response['status']
            self.data_grid['hedge_line']['client_order_id'] = response['clientOrderId']
            
            # log sucess post
            logging.info(f"{self.operation_code} ✅ {self.data_grid['hedge_line']['entry']} ({round(self.data_grid['hedge_line']['distance']*100, 2)}%) | "
                  f"{self.data_grid['hedge_line']['price']} | {self.data_grid['hedge_line']['quantity']} | "
                  f"{self.data_grid['hedge_line']['cost']}")
            
        except Exception as e:
            logging.exception(f"{self.operation_code} Error placing hedge order: {e}")

        return None
    
    # post entry order
    def post_sl_order(self):
        logging.debug(f"{self.operation_code} POSTING STOP_LOSS ORDER TO BINANCE...")
        try:
            # Post the stop loss order
            response = self.client.futures_create_order(
                symbol = self.data_grid['symbol']['value'],
                side = self.data_grid['stop_loss_line']['side'],  # SL for LONG is SELL and vice versa
                positionSide = self.data_grid['stop_loss_line']['position_side'],
                type='STOP_MARKET',
                stopPrice=self.data_grid['stop_loss_line']['price'],
                closePosition=True,
                newClientOrderId=f"{self.operation_code}_SL_0_{str(uuid.uuid4())[:5]}"
            )

            # Update stop loss line with response data
            self.data_grid['stop_loss_line']['order_id'] = response.get('orderId', 0)
            self.data_grid['stop_loss_line']['status'] = response.get('status', 'UNKNOWN')
            self.data_grid['stop_loss_line']['client_order_id'] = response.get('clientOrderId', 'UNKNOWN')
            
            # Log the placed order details
            logging.debug(f"{self.operation_code} stop_loss_line posted to binance: {self.data_grid['stop_loss_line']}")
            logging.debug(f"{self.operation_code} stop_loss_line binance response: {response}")
            
            # Log successful stop loss order
            logging.info(f"{self.operation_code} ✅ {self.data_grid['stop_loss_line']['entry']} ({round(self.data_grid['stop_loss_line']['distance']*100, 2)}%) | "
                  f"{self.data_grid['stop_loss_line']['price']} | {self.data_grid['stop_loss_line']['quantity']} | "
                  f"{self.data_grid['stop_loss_line']['cost']}")

        except Exception as e:
            logging.exception(f"{self.operation_code} Error placing stop loss order: {e}")

        return None


    # post take profit order
    def post_tp_order(self):
        logging.debug(f"{self.operation_code} POSTING TAKE PROFIT ORDER TO BINANCE...")
        try:
            # Post the take profit order
            response = self.client.futures_create_order(
                symbol=self.data_grid['symbol']['value'],
                side=self.data_grid['take_profit_line']['side'],  # TP for LONG is SELL and vice versa
                positionSide=self.data_grid['take_profit_line']['position_side'],
                type='TAKE_PROFIT_MARKET',
                stopPrice=self.data_grid['take_profit_line']['price'],
                closePosition=True,
                newClientOrderId=f"{self.operation_code}_TP_0_{str(uuid.uuid4())[:5]}"
            )

            # Update take profit line with response data
            self.data_grid['take_profit_line']['order_id'] = response.get('orderId', 0)
            self.data_grid['take_profit_line']['status'] = response.get('status', 'UNKNOWN')
            self.data_grid['take_profit_line']['client_order_id'] = response.get('clientOrderId', 'UNKNOWN')
            
            # Log the placed order details
            logging.debug(f"{self.operation_code} take_profit_line posted to binance: {self.data_grid['take_profit_line']}")
            logging.debug(f"{self.operation_code} take_profit_line binance response: {response}")
            
            # Log the successful order
            logging.info(f"{self.operation_code} ✅ {self.data_grid['take_profit_line']['entry']} ({round(self.data_grid['take_profit_line']['distance']*100,2)}%) | "
                  f"{self.data_grid['take_profit_line']['price']} | {self.data_grid['take_profit_line']['quantity']} | "
                  f"{self.data_grid['take_profit_line']['cost']}")
            
        except Exception as e:
            logging.exception(f"{self.operation_code} Error placing take profit order: {e}")

        return None
    

    # post unload order
    def post_ul_order(self):
        logging.debug(f"{self.operation_code} POSTING UNLOAD ORDER...")
        try:
            # Calculate the unload price based on the side (LONG or SHORT)
            price_factor = 1 + self.data_grid['unload_line']['distance'] if self.data_grid['side']['value'] == 'LONG' else 1 - self.data_grid['unload_line']['distance']
            self.data_grid['unload_line']['price'] = self.round_to_tick_size(self.data_grid['current_line']['price'] * price_factor)

            # Calculate unload quantity
            self.data_grid['unload_line']['quantity'] = round(
                self.data_grid['current_line']['quantity'] - self.data_grid['entry_line']['quantity'], # always take the original quantity inserted
                self.data_grid['quantity_precision']
            )
            
            logging.debug(f"{self.operation_code} unload_line to post: {self.data_grid['unload_line']}")

            # Post the limit order
            response = self.client.futures_create_order(
                symbol=self.data_grid['symbol']['value'],
                side=self.data_grid['unload_line']['side'],
                type='LIMIT',
                timeInForce='GTC',
                positionSide=self.data_grid['unload_line']['position_side'],
                price=self.data_grid['unload_line']['price'],
                quantity=self.data_grid['unload_line']['quantity'],
                newClientOrderId=f"{self.operation_code}_UL_0_{str(uuid.uuid4())[:5]}"
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

    # update current position into current line
    def update_current_position(self):
        
        logging.debug(f"{self.operation_code} UPDATING CURRENT POSITION FROM BINANCE...")
        
        try:
            # Fetch futures position information
            response = self.client.futures_position_information(symbol=self.data_grid['symbol']['value'])

            # Loop through the list to find the relevant position based on 'positionSide'
            for position_info in response:
                if float(position_info['positionAmt']) != 0:  # Skip empty positions if the exchange is in hedge mode the response 2 current position, one is 0
                    self.data_grid['current_line']['price'] = self.round_to_tick_size(float(position_info['entryPrice']))
                    self.data_grid['current_line']['quantity'] = round(abs(float(position_info['positionAmt'])), self.data_grid['quantity_precision'])
                    self.data_grid['current_line']['position_side'] = position_info['positionSide']
                    
                    logging.debug(f"{self.operation_code} Current position from Binance: {position_info}")
                    logging.debug(f"{self.operation_code} Current position on current_line: {self.data_grid['current_line']}")
                    
                    break  # Exit after finding the first non-empty position

        except Exception as e:
            logging.exception(f"{self.operation_code} update_current_position | Error fetching position information for {self.data_grid['symbol']}: {e}")

