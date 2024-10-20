from datetime import datetime
import os
import uuid
import json
from binance.client import Client
import math
import logging
import time

# Reading json file, the json_file_path should include directory + file + .json extension
def read_config_data(json_file_path):
    try:
        # Attempt to load file
        if os.path.isfile(json_file_path):
            with open(json_file_path, 'r') as file:
                config_file = json.load(file)
                logging.debug(f"Successfully loaded data_grid file: {json_file_path}")
                return config_file
        else:
            logging.warning(f"data_grid file '{json_file_path}' not found")
    except (FileNotFoundError, KeyError):
        logging.exception("Error: Invalid config.json file or not found. Please check the file path and format.")
        print(f"Error: Invalid {json_file_path} file or not found. Please check the file path and format.")
        return 

# Writting json data grid file
def write_config_data(directory, file_name, data_grid):
    os.makedirs(directory, exist_ok=True) # if directory doesn't exist, it will be created
    xfile = f"{directory}/{file_name}" # file name should have extension to
    with open(xfile, 'w') as file:
        json.dump(data_grid, file, indent=4)  # Pretty-print JSON
    return None

def update_config():
    # updating exchange info
    directory = 'config'
    file_name = 'exchange_info.json'
    mod_time = os.path.getmtime(f"{directory}/{file_name}")
    mod_datetime = datetime.fromtimestamp(mod_time)
    current_time = datetime.now()
    
    time_difference = current_time - mod_datetime
    days_since_mod = time_difference.days
    
    if days_since_mod > 1: # if the file has more than 1 day then get exchange info and overwrite
        client = get_connection()
        info = client.get_exchange_info()
        write_config_data(directory, file_name, info)
    
        # getting wallet balance
        usdt_balance = next((b['balance'] for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0)
        data_grid = read_config_data('config/config.json')
        data_grid['wallet_balance_usdt'] = usdt_balance
        write_config_data(directory, 'config.json', data_grid) # updating wallet balance
    
    return None

# input data from console
def input_data(config_file):
    logging.debug(f"INPUT DATA...")
    # Helper to safely get user input with default fallback
    def get_input(prompt, default_value=None, cast_func=str):
        user_input = input(prompt).strip()
        return cast_func(user_input) if user_input else default_value
    
    update_config() # update config
    #client = get_connection()  # Open Binance connection

    # Asking for INPUT symbol
    if config_file['symbol']['input']:   
        config_file['symbol']['value'] = get_input("Token Pair like (BTC): ", "BTC").upper() + "USDT"

    # Getting precisions for the symbol
    info = read_config_data('config/exchange_info.json')['symbols']
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
        config_file['side']['value'] = get_input("Grid Side (LONG): ", "LONG", str).upper()

    # INPUT entry price
    if config_file['entry_price']['input']:
        tick_increment = int(abs(math.log10(config_file['tick_size'])))
        config_file['entry_price']['value'] = round(get_input("Entry Price: ", 0.0, float), tick_increment)

    # INPUT grid distance
    if config_file['grid_distance']['input']:
        config_file['grid_distance']['value'] = get_input("Grid Distance (2%): ", 2, float) / 100 # default valur for grid distance is 2%

    # INPUT token increment
    if config_file['quantity_increment']['input']:
        config_file['quantity_increment']['value'] = get_input("Token Increment (40%): ", 40, float) / 100 # default increment is 40%

    # Compound calculation
    if config_file['compound']['enabled']:
        # Get wallet balance
        usdt_balance = config_file['wallet_balance_usdt']
        config_file['compound']['quantity'] = round(float(usdt_balance) * config_file['compound']['risk'], 2)
        config_file['stop_loss_amount']['value'] = config_file['compound']['quantity']
        config_file['entry_quantity']['value'] = round(config_file['compound']['quantity'] / config_file['entry_price']['value'], config_file['quantity_precision']) # convert risk proportion of wallet (compound) to entry quantity
        config_file['stop_loss_amount']['input'] = False
        config_file['entry_quantity']['input'] = False

    # INPUT stop_loss_amount
    if config_file['stop_loss_amount']['input']:
        config_file['stop_loss_amount']['value'] = get_input("Stop Loss Amount ($10): ", 10.0, float)
    
    # INPUT quantity
    if config_file['entry_quantity']['input']: # if entry quantity is enabled
        if config_file['entry_quantity']['on_stable'] == True: # if on_stable is enabled, the input will be in USDT not in tokens
            entry_q = round(get_input("Entry Quantity ($10): ", 10.0, float), 2) # getting quantity in USDT
            config_file['entry_quantity']['value'] = round(entry_q / config_file['entry_price']['value'], config_file['quantity_precision']) #converting USDT entry to tokens

        if config_file['entry_quantity']['on_stable'] == False: # if on_stable is false, then the input will get quantity as tokens
            config_file['entry_quantity']['value'] = round(get_input(f"Entry Quantity of ({config_file['symbol']['value']}): ", 0.0, float), config_file['quantity_precision'])
    
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

    
    # Generate operation code
    #operation_code = gen_date_code() + "-" + str(config_file['symbol']['value'])[:-4] + "-" + str(config_file['side']['value'])[0]
    operation_code = config_file['symbol']['value'] + "-" + config_file['side']['value']
    config_file['operation_code'] = operation_code

    # writting to data grid
    write_config_data('ops', operation_code + ".json", config_file)
        
    return operation_code



# Define get_connection outside the class
def get_connection():
    try:
        # Load credentials from JSON file
        with open('../credentials.json', 'r') as file:
            binance_credentials = json.load(file)
            api_key = binance_credentials['api_key']
            api_secret = binance_credentials['api_secret']

        # Initialize the Binance client
        client = Client(api_key, api_secret)
        client.ping()  # Ensure connection
        client.get_server_time() # getting server time from binance
        # Enable time synchronization
        client.timestamp_offset = client.get_server_time()['serverTime'] - int(time.time() * 1000)
        return client
    
    except FileNotFoundError:
        logging.FileNotFoundError("Error: credentials.json file not found. Please check the file path.")
        logging.info("Error: credentials.json file not found. Please check the file path.")
    except KeyError:
        logging.KeyError("Error: Invalid format in credentials.json. Missing 'api_key' or 'api_secret'.")
        logging.info("Error: Invalid format in credentials.json. Missing 'api_key' or 'api_secret'.")
    except Exception as e:
        logging.exception(f"Binance connection error, check credentials or internet: {e}")
        logging.info(f"Binance connection error, check credentials or internet: {e}")
    
    return None  # Return None explicitly if the connection fails


    


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
        
        # Calculate the take profit price based on the side
        price_factor = 1 + self.data_grid['take_profit_line']['distance'] if self.data_grid['side']['value'] == 'LONG' else 1 - self.data_grid['take_profit_line']['distance']
        self.data_grid['take_profit_line']['price'] = self.round_to_tick_size(self.data_grid['entry_line']['price'] * price_factor)
        logging.debug(f"{self.operation_code} take_profit_line generated: {self.data_grid['take_profit_line']}")
        
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
                newClientOrderId = f"IN_{self.operation_code}_{str(uuid.uuid4())[:5]}"
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

    
    # clean entire grid
    def clean_order(self, code):
        
        logging.debug(f"{self.operation_code} CLEANING {code.upper()} ORDERS...")
        symbol = self.data_grid['symbol']['value']
        order_code = f"{code.upper()}_{self.operation_code}" #code to lookfor on orders
        open_orders = self.client.futures_get_open_orders(symbol=symbol) # getting all open orders

        if not open_orders:
            logging.info(f"{self.operation_code} No {code.upper()} orders to cancel.")
            return
        
        # cleaning orders
        for order in open_orders:
            if order['clientOrderId'][:-6] == order_code:
                try:
                    response = self.client.futures_cancel_order(symbol=symbol, orderId=order['orderId']) # Cancelling order
                
                except Exception as e:
                    logging.exception(f"{self.operation_code} Error cancelling order: {e} ")

        # Clear grid_body after all cancellations
        logging.info(f"{self.operation_code} All {code.upper()} orders cancelled and cleared.")

            
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
                    newClientOrderId = "GD" + "_" + self.operation_code + "_" + str(uuid.uuid4())[:5]
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
                
    
    # post entry order
    def post_sl_order(self):
        logging.debug(f"{self.operation_code} POSTING STOP_LOSS ORDER TO BINANCE...")
        try:
            # Post the stop loss order
            response = self.client.futures_create_order(
                symbol=self.data_grid['symbol']['value'],
                side=self.data_grid['stop_loss_line']['side'],  # SL for LONG is SELL and vice versa
                positionSide=self.data_grid['stop_loss_line']['position_side'],
                type='STOP_MARKET',
                stopPrice=self.data_grid['stop_loss_line']['price'],
                closePosition=True,
                newClientOrderId=f"SL_{self.operation_code}_{str(uuid.uuid4())[:5]}"
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
                newClientOrderId=f"TP_{self.operation_code}_{str(uuid.uuid4())[:5]}"
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
                newClientOrderId=f"UL_{self.operation_code}_{str(uuid.uuid4())[:5]}"
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


    def clean_open_orders(self):
        
        logging.debug(f"{self.operation_code} CLEAN ALL OPEN ORDERS...")
        op_symbol = self.data_grid['symbol']['value']
        
        # getting all open orders
        try:
            open_orders = self.client.futures_get_open_orders(symbol=op_symbol)
        
        except Exception:
            logging.exception("{self.operation_code} There is no open orders")
            
        for order in open_orders:
            try:
                # Cancel multiple orders at once
                response = self.client.futures_cancel_order(symbol=op_symbol, orderId=order['orderId'])
                logging.debug(f"{self.operation_code} Order to cancel: {order}")
                logging.debug(f"{self.operation_code} Binance response to cancel: {response}")
                logging.info(f"{self.operation_code} ⛔️ {response['type']} | Price: {response['price']} | Quantity: {response['origQty']}")
            except Exception as e:
                logging.exception(f"{self.operation_code} Error cancelling orders: {e} ")

        # Clear grid_body after all cancellations
        logging.info(f"{self.operation_code} All grid orders cancelled and cleared.")
    

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

            
    def print_grid(self):
        try:
            # Print entry line
            print(f"{self.data_grid['entry_line']['entry']} | {self.data_grid['entry_line']['price']} | {self.data_grid['entry_line']['quantity']} | {self.data_grid['entry_line']['cost']}")

            # Print grid body
            for line in self.data_grid['grid_body']:
                print(f"{line['entry']} | {line['price']} | {line['quantity']} | {line['cost']}")

            # Print stop loss line
            print(f"{self.data_grid['stop_loss_line']['entry']} ({self.data_grid['stop_loss_line']['distance'] * 100:.2f}%) | "
              f"{self.data_grid['stop_loss_line']['price']} | {self.data_grid['stop_loss_line']['quantity']} | "
              f"{self.data_grid['stop_loss_line']['cost']}")
    
        except KeyError as e:
            print(f"Missing key in data: {e}")
        except Exception as e:
            print(f"Error while printing grid: {e}")


    







