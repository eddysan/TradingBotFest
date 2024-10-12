from datetime import datetime
import os
import uuid
import json
from binance.client import Client
import math
import logging


# generate operation code
def gen_date_code():
    # Get the current date and time
    now = datetime.now()

    # Format the date and time as "YYYYMMDDHHmm"
    formatted_code = now.strftime("%m%d%H%M")

    return formatted_code

# input data from console
def input_data():
    # Helper to safely get user input with default fallback
    def get_input(prompt, default_value=None, cast_func=str):
        user_input = input(prompt).strip()
        return cast_func(user_input) if user_input else default_value

    # Reading default config file
    try:
        with open('config.json', 'r') as file:
            config_file = json.load(file)
    except (FileNotFoundError, KeyError):
        logging.exception("Error: Invalid config.json file or not found. Please check the file path and format.")
        print("Error: Invalid config.json file or not found. Please check the file path and format.")
        return
    
    client = get_connection()  # Open Binance connection

    # INPUT symbol
    config_file['symbol'] = get_input("Token Pair like (BTC): ", "BTC").upper() + "USDT"

    # Getting precisions for the symbol
    info = client.futures_exchange_info()['symbols']
    symbol_info = next((x for x in info if x['symbol'] == config_file['symbol']), None)
    
    # Retrieve precision filters
    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            config_file['step_size'] = float(f['stepSize'])
        elif f['filterType'] == 'PRICE_FILTER':
            config_file['tick_size'] = float(f['tickSize'])
    
    config_file['price_precision'] = symbol_info['pricePrecision']
    config_file['quantity_precision'] = symbol_info['quantityPrecision']

    # INPUT side (default to LONG)
    config_file['side'] = get_input("Grid Side (LONG): ", "LONG", str).upper()

    # INPUT entry price
    tick_increment = int(abs(math.log10(config_file['tick_size'])))
    config_file['entry_line']['price'] = round(get_input("Entry Price: ", 0.0, float), tick_increment)

    # INPUT grid distance
    config_file['grid_distance'] = get_input("Grid Distance (2%): ", 2.0, float) / 100

    # INPUT token increment
    config_file['quantity_increment'] = get_input("Token Increment (40%): ", 40.0, float) / 100

    # Compound calculation
    if config_file['compound']['enabled']:
        # Get wallet balance
        usdt_balance = next((b['balance'] for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0)
        config_file['compound']['quantity'] = round(float(usdt_balance) * config_file['compound']['risk'], 2)
        config_file['stop_loss_amount'] = config_file['compound']['quantity']
    else:
        # INPUT stop loss amount
        config_file['stop_loss_amount'] = get_input("Stop Loss Amount ($10): ", 10.0, float)
    
    # INPUT quantity or compound quantity
    quantity = config_file['compound']['quantity'] if config_file['compound']['enabled'] else get_input("Entry Quantity ($10): ", 10.0, float)
    config_file['entry_line']['quantity'] = round(quantity / config_file['entry_line']['price'], config_file['quantity_precision'])
    #config_file['entry_line']['quantity'] = round(get_input("Entry Quantity: ", 0.0, float), config_file['quantity_precision'])

    # saving grid body    
    config_file['grid_body'] = []


    # processing entry line
    config_file['entry_line']["side"] = 'BUY' if config_file['side'] == 'LONG' else 'SELL'
    config_file['entry_line']["position_side"] = config_file['side']
    config_file['entry_line']["cost"] = round(config_file['entry_line']["price"] * config_file['entry_line']["quantity"], 2)
                       
    # processing take profit
    config_file['take_profit_line']['side'] = 'SELL' if config_file['side'] == 'LONG' else 'BUY' #if the operation is LONG then the TP should be SELL and viceversa
    config_file['take_profit_line']['position_side'] = config_file['side'] #mandatory for hedge mode
    
    # unload
    config_file['unload_line']['side'] = 'SELL' if config_file['side'] == 'LONG' else 'BUY' # limit order to unload plus quantity of tokens
    config_file['unload_line']['position_side'] = config_file['side']
    
    # stop loss
    config_file['stop_loss_line']['side'] = 'SELL' if config_file['side'] == 'LONG' else 'BUY' #if the operation is LONG then the SL should be SELL
    config_file['stop_loss_line']['position_side'] = config_file['side']
    
    # current line is the pivot that store que current price in operation, this will change if the grid has chaged
    config_file['current_line']['price'] = config_file['entry_line']['price']
    config_file['current_line']['quantity'] = config_file['entry_line']['quantity']
    config_file['current_line']['position_side'] = config_file['entry_line']['position_side']

    # Generate operation code
    operation_code = gen_date_code() + "-" + str(config_file['symbol'])[:-4] + "-" + str(config_file['side'])[0]
    config_file['operation_code'] = operation_code

    # Create data_grid file to operations folder
    os.makedirs('ops', exist_ok=True)
    xfile = f"ops/{operation_code}.json"
    with open(xfile, 'w') as file:
        json.dump(config_file, file, indent=4)  # Pretty-print JSON

    # Create log file
    

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
        return client
    
    except FileNotFoundError:
        print("Error: credentials.json file not found. Please check the file path.")
    except KeyError:
        print("Error: Invalid format in credentials.json. Missing 'api_key' or 'api_secret'.")
    except Exception as e:
        print(f"Binance connection error, check credentials or internet: {e}")
    
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
        return self.data_grid['symbol']
    
    # read data grid in order to upload config
    def read_data_grid(self):
        logging.info("READING DATA_GRID FILE...")
        operation_file = f"ops/{self.operation_code}.json"
        fallback_file = "config.json"  # The fallback file

        try:
            # Attempt to load the primary file
            if os.path.isfile(operation_file):
                with open(operation_file, 'r') as file:
                    config_file = json.load(file)
                    logging.info(f"Successfully loaded data_grid file: {operation_file}")
                    return config_file
            else:
                logging.warning(f"data_grid file '{operation_file}' not found. Attempting to load fallback config.json file.")

            # Attempt to load the fallback file if primary doesn't exist
            if os.path.isfile(fallback_file):
                with open(fallback_file, 'r') as file:
                    config_file = json.load(file)
                    logging.info(f"Successfully loaded fallback file: {fallback_file}")
                    return config_file
            else:
                logging.error(f"Fallback config.json file '{fallback_file}' not found.")
                return None

        except json.JSONDecodeError as e:
            logging.error(f"JSONDecodeError in file: {operation_file if os.path.isfile(operation_file) else fallback_file} - {str(e)}")
            print(f"JSONDecodeError in file: {operation_file if os.path.isfile(operation_file) else fallback_file} - {str(e)}")
            return None

        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            return None
        
        
    # Write data grid to operations folder
    def write_data_grid(self):
        logging.info("WRITTING DATA_GRID FILE...")
        cfile = f"ops/{self.operation_code}.json"

        try:
            # Writing the JSON data to the file
            with open(cfile, 'w') as file:
                json.dump(self.data_grid, file, indent=4)
                logging.info(f"Successfully saved data_grid to {cfile}.")

        except IOError as e:
            # Log the error with exception traceback
            logging.exception(f"Error writing file {self.operation_code}: {e}")
        except Exception as e:
            # Catch any other unexpected exceptions
            logging.exception(f"Unexpected error occurred while writing to {cfile}: {str(e)}")

    
    
    # round price to increment accepted by binance
    def round_to_tick_size(self, price):
        tick_increment = int(abs(math.log10(self.data_grid['tick_size'])))
        return round(price, tick_increment)
    
    
    # generate the entire grid points, stop loss and take profit
    def generate_grid(self):
        
        logging.info("GENERATING DATA_GRID...")
        
        # clean and initialize working variables
        self.data_grid['grid_body'] = [] #cleaning grid body before operations
        current_price = self.data_grid['entry_line']["price"]
        current_quantity = self.data_grid['entry_line']["quantity"]
        
        self.data_grid['average_line']['price'] = self.data_grid['entry_line']["price"]
        self.data_grid['average_line']['quantity'] = self.data_grid['entry_line']["quantity"]

        # set stop loss taking the first point, entry line
        self.data_grid['average_line']['sl_distance'] = (self.data_grid['stop_loss_amount'] * 100) / (self.data_grid['average_line']['price'] *  self.data_grid['average_line']['quantity'])
        
        if self.data_grid['side'] == 'LONG':
            self.data_grid['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid['average_line']['price'] - (self.data_grid['average_line']['price'] * self.data_grid['average_line']['sl_distance'] / 100) )
            self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['entry_line']['price'] - self.data_grid['stop_loss_line']['price']) / self.data_grid['entry_line']['price'],4)
            
        if self.data_grid['side'] == 'SHORT':
                self.data_grid['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid['average_line']['price'] + (self.data_grid['average_line']['price'] * self.data_grid['average_line']['sl_distance'] / 100) )
                self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['stop_loss_line']['price'] - self.data_grid['entry_line']['price']) / self.data_grid['entry_line']['price'],4)

        while True:
            
            # increment as grid distance the price and quantity
            if self.data_grid['side'] == 'LONG':
                new_price = current_price * (1 - self.data_grid['grid_distance'])
            
            if self.data_grid['side'] == 'SHORT':
                new_price = current_price * (1 + self.data_grid['grid_distance'])
            
            new_quantity = current_quantity * (1 + self.data_grid['quantity_increment'])
            
            # control if the new price is greater or lower than stop loss price, in order to stop generation of posts
            if self.data_grid['side'] == 'LONG':
                if self.data_grid['stop_loss_line']['price'] > new_price:
                    break
                
            if self.data_grid['side'] == 'SHORT':
                if new_price > self.data_grid['stop_loss_line']['price']:
                    break
            
            self.data_grid['grid_body'].append({"entry" : len(self.data_grid['grid_body'])+1,
                                   "side": 'BUY' if self.data_grid['side'].upper() == 'LONG' else 'SELL',
                                   "position_side": self.data_grid['side'].upper(),
                                   "price" : self.round_to_tick_size(new_price), 
                                   "quantity" : round(new_quantity, self.data_grid['quantity_precision']), 
                                   "cost" : round(new_price * new_quantity, 2),
                                   })
            
            
            # calculate the average price and accumulated quantity if the position is taken
            self.data_grid['average_line']['price'] = self.round_to_tick_size( ((self.data_grid['average_line']['price'] * self.data_grid['average_line']['quantity']) + (new_price * new_quantity)) / (self.data_grid['average_line']['quantity'] + new_quantity)) 
            self.data_grid['average_line']['quantity'] = round(self.data_grid['average_line']['quantity'] + new_quantity, self.data_grid['quantity_precision'])
            
            self.data_grid['average_line']['sl_distance'] = (self.data_grid['stop_loss_amount'] * 100) / (self.data_grid['average_line']['price'] *  self.data_grid['average_line']['quantity'])
            
            if self.data_grid['side'] == 'LONG':
                self.data_grid['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid['average_line']['price'] - (self.data_grid['average_line']['price'] * self.data_grid['average_line']['sl_distance'] / 100) )
                self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['entry_line']['price'] - self.data_grid['stop_loss_line']['price']) / self.data_grid['entry_line']['price'],4)
            
            if self.data_grid['side'] == 'SHORT':
                self.data_grid['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid['average_line']['price'] + (self.data_grid['average_line']['price'] * self.data_grid['average_line']['sl_distance'] / 100) )
                self.data_grid['stop_loss_line']['distance'] = round((self.data_grid['stop_loss_line']['price'] - self.data_grid['entry_line']['price']) / self.data_grid['entry_line']['price'],4)

            
            current_price = new_price
            current_quantity = new_quantity
            
        logging.debug(f"data_grid[grid_body]: {self.data_grid['grid_body']}")
        logging.debug(f"data_grid[stop_loss_line]: {self.data_grid['stop_loss_line']}")
        
        # Calculate the take profit price based on the side
        price_factor = 1 + self.data_grid['take_profit_line']['distance'] if self.data_grid['side'].upper() == 'LONG' else 1 - self.data_grid['take_profit_line']['distance']
        self.data_grid['take_profit_line']['price'] = self.round_to_tick_size(self.data_grid['entry_line']['price'] * price_factor)
        logging.debug(f"data_grid[take_profit_line]: {self.data_grid['take_profit_line']}")
        
        logging.info(f"Grid generation completed. Stop loss at {self.data_grid['stop_loss_line']['price']}, take profit at {self.data_grid['take_profit_line']['price']}")
        
        return None
    
            
    # update entry line data taking current line as data, and the current position will be the new entry
    def update_entry_line(self):
        logging.info("UPDATING ENTRY LINE FROM CURRENT LINE...")
        current_line = self.data_grid['current_line']
        entry_line = self.data_grid['entry_line']
    
        # Update entry line with current line values
        entry_line['price'] = current_line['price']
        entry_line['quantity'] = current_line['quantity']
        entry_line['cost'] = round(entry_line['price'] * entry_line['quantity'], 2)
        
        logging.debug(f"current_line: {self.data_grid['current_line']}")
        logging.debug(f"entry_line: {self.data_grid['entry_line']}")
        
        return None
    
    
    # post entry order
    def post_entry_order(self):

        logging.info("POSTING ENTRY ORDER TO BINANCE...")
        entry_line = self.data_grid.get('entry_line', {})
    
        try:
            # Create the entry order
            response = self.client.futures_create_order(
                symbol = self.data_grid['symbol'].upper(),
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
            logging.debug(f"entry_line posted to binance: {entry_line}")
            logging.debug(f"Binance response: {response}")
            print(f"{self.data_grid['symbol']} - {entry_line.get('entry', 'N/A')} | {entry_line['price']} | {entry_line['quantity']} | {entry_line.get('cost', 'N/A')} ✔️")

        except Exception as e:
            logging.exception(f"Error placing entry_line order: {entry_line} \n {e}")
            print(f"Error placing entry_line order: {e}")

        return None

    
    # clean entire grid
    def clean_grid_order(self):
        
        logging.info("CLEANING ACTIVE GRID ORDERS...")
        dg_symbol = self.data_grid['symbol']
        order_list = self.data_grid.get('grid_body', [])

        if not order_list:
            print("No grid orders to cancel.")
            return

        for order in order_list:
            try:
                # Cancel multiple orders at once
                response = self.client.futures_cancel_order(symbol=dg_symbol, orderId=order['order_id'])
                
            except Exception as e:
                logging.exception(f"Error cancelling orders: {e} ")
                print(f"Error cancelling orders: {e} ")

        # Clear grid_body after all cancellations
        self.data_grid['grid_body'] = []
        print("All grid orders cancelled and cleared.")

            
    # post a limit order for grid body
    def post_grid_order(self):
        logging.info("POSTING GRID_BODY TO BINANCE...")
        try:
            for i in range(len(self.data_grid['grid_body'])):
                response = self.client.futures_create_order(
                    symbol = self.data_grid['symbol'].upper(),
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
                
                logging.debug(f"Posting grid line to binance: {self.data_grid['grid_body'][i]}")
                logging.debug(f"Binance response: {response}")
                print(f"{self.data_grid['symbol']} - {self.data_grid['grid_body'][i]['entry']} | {self.data_grid['grid_body'][i]['price']} | {self.data_grid['grid_body'][i]['quantity']} | {self.data_grid['grid_body'][i]['cost']}  ✔️")
                
        except KeyError as e:
            logging.exception(f"Posting grid orders: Missing key in order data: {e}")
            print(f"Missing key in order data: {e}")
        except Exception as e:
            logging.exception(f"Error posting grid data: {e}")
            print(f"Error posting order: {e}")
    
       
    # clean stop loss order
    def clean_sl_order(self):
        logging.info("CLEANING STOP LOSS ORDER FROM BINANCE...")
        
        order_id = self.data_grid['stop_loss_line'].get('order_id', 0)
     
        # Check if there is an existing stop loss order to cancel
        if order_id:
            try:
                self.client.futures_cancel_order(symbol=self.data_grid['symbol'], orderId=order_id)
                self.data_grid['stop_loss_line']['price'] = 0
                self.data_grid['stop_loss_line']['quantity'] = 0
                self.data_grid['stop_loss_line']['order_id'] = 0
                self.data_grid['stop_loss_line']['client_order_id'] = "SL_"
            except Exception as e:
                logging.exception(f"Error cancelling stop loss order {order_id} for {self.data_grid['symbol']}: {e}")
                print(f"Error cancelling stop loss order {order_id} for {self.data_grid['symbol']}: {e}")
            
    
    # post entry order
    def post_sl_order(self):
        logging.info("POSTING STOP LOSS ORDER TO BINANCE...")
        try:
            # Post the stop loss order
            response = self.client.futures_create_order(
                symbol=self.data_grid['symbol'].upper(),
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
            logging.debug(f"stop_loss_line posted to binance: {self.data_grid['stop_loss_line']}")
            logging.debug(f"stop_loss_line binance response: {response}")
            
            # Log successful stop loss order
            print(f"{self.data_grid['symbol']} - {self.data_grid['stop_loss_line']['entry']} ({round(self.data_grid['stop_loss_line']['distance']*100, 2)}%) | "
                  f"{self.data_grid['stop_loss_line']['price']} | {self.data_grid['stop_loss_line']['quantity']} | "
                  f"{self.data_grid['stop_loss_line']['cost']} ✔️")

        except Exception as e:
            logging.exception(f"Error placing stop loss order: {e}")
            print(f"Error placing stop loss order: {e}")

        return None




    # clean take profit order
    def clean_tp_order(self):
        logging.info("CLEANING TAKE PROFIT ORDERS FROM BINANCE...")
        
        order_id = self.data_grid['take_profit_line'].get('order_id', 0)
     
        # Check if there is an existing unload order to cancel
        if order_id:
            try:
                self.client.futures_cancel_order(symbol=self.data_grid['symbol'], orderId=order_id)
                self.data_grid['take_profit_line']['price'] = 0
                self.data_grid['take_profit_line']['quantity'] = 0
                self.data_grid['take_profit_line']['order_id'] = 0
                self.data_grid['take_profit_line']['client_order_id'] = "TP_"
            except Exception as e:
                logging.exception(f"Error cancelling take profit order {order_id} for {self.data_grid['symbol']}: {e}")
                print(f"Error cancelling take profit order {order_id} for {self.data_grid['symbol']}: {e}")
            

    # post take profit order
    def post_tp_order(self):
        logging.info("POSTING TAKE PROFIT ORDER TO BINANCE...")
        try:
            # Post the take profit order
            response = self.client.futures_create_order(
                symbol=self.data_grid['symbol'].upper(),
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
            logging.debug(f"take_profit_line posted to binance: {self.data_grid['take_profit_line']}")
            logging.debug(f"take_profit_line binance response: {response}")
            
            # Log the successful order
            print(f"{self.data_grid['symbol']} - {self.data_grid['take_profit_line']['entry']} ({round(self.data_grid['take_profit_line']['distance']*100,2)}%) | "
                  f"{self.data_grid['take_profit_line']['price']} | {self.data_grid['take_profit_line']['quantity']} | "
                  f"{self.data_grid['take_profit_line']['cost']} ✔️")
            
        except Exception as e:
            logging.exception(f"Error placing take profit order: {e}")
            print(f"Error placing take profit order: {e}")

        return None
    
    
    # clean unload order
    def clean_ul_order(self):
        logging.info("CLEANING UNLOAD LINE...")
        order_id = self.data_grid['unload_line'].get('order_id', 0)
    
        # Check if there is an existing unload order to cancel
        if order_id:
            try:
                response = self.client.futures_cancel_order(symbol=self.data_grid['symbol'], orderId=order_id)
                self.data_grid['unload_line']['price'] = 0
                self.data_grid['unload_line']['quantity'] = 0
                self.data_grid['unload_line']['order_id'] = 0
                self.data_grid['unload_line']['client_order_id'] = "UL_"
                logging.debug(f"unload_line to cancel: {self.data_grid['unload_line']}")
                logging.debug(f"canceling unload_line, binance response: {response}")
            
            except Exception as e:
                logging.exception(f"Error cancelling unload_line {order_id} for {self.data_grid['symbol']}: {e}")
                print(f"Error cancelling unload_line {order_id} for {self.data_grid['symbol']}: {e}")
        
    
    # post unload order
    def post_ul_order(self):
        logging.info("POSTING UNLOAD ORDER...")
        try:
            # Calculate the unload price based on the side (LONG or SHORT)
            price_factor = 1 + self.data_grid['unload_line']['distance'] if self.data_grid['side'].upper() == 'LONG' else 1 - self.data_grid['unload_line']['distance']
            self.data_grid['unload_line']['price'] = self.round_to_tick_size(self.data_grid['current_line']['price'] * price_factor)

            # Calculate unload quantity
            self.data_grid['unload_line']['quantity'] = round(
                self.data_grid['current_line']['quantity'] - self.data_grid['entry_line']['quantity'],
                self.data_grid['quantity_precision']
            )
            
            logging.debug(f"unload_line to post: {self.data_grid['unload_line']}")

            # Post the limit order
            response = self.client.futures_create_order(
                symbol=self.data_grid['symbol'].upper(),
                side=self.data_grid['unload_line']['side'],
                type='LIMIT',
                timeInForce='GTC',
                positionSide=self.data_grid['unload_line']['position_side'],
                price=self.data_grid['unload_line']['price'],
                quantity=self.data_grid['unload_line']['quantity'],
                newClientOrderId=f"UL_{self.operation_code}_{str(uuid.uuid4())[:5]}"
            )

            # Update unload line with the response data
            self.data_grid['unload_line']['order_id'] = response.get('orderId', 0)
            self.data_grid['unload_line']['status'] = response.get('status', 'UNKNOWN')
            self.data_grid['unload_line']['client_order_id'] = response.get('clientOrderId', 'UNKNOWN')

            logging.debug(f"unload_line response from binance: {response}")
            
            # Log the success message
            print(f"UL: {self.data_grid['symbol']} - {self.data_grid['unload_line']['entry']} | "
                  f"{self.data_grid['unload_line']['price']} | {self.data_grid['unload_line']['quantity']} ✔️")
        
        except KeyError as e:
            logging.exception(f"Missing key in order data: {e}")
            print(f"Missing key in order data: {e}")
        except Exception as e:
            logging.exception(f"Error posting order: {e}")
            print(f"Error posting order: {e}")



    def clean_open_orders(self):
        
        logging.info("CLEAN ALL OPEN ORDERS...")
        op_symbol = self.data_grid['symbol']
        
        # getting all open orders
        try:
            open_orders = self.client.futures_get_open_orders(symbol=op_symbol)
        
        except Exception:
            logging.exception("There is no open orders")
            print("There is no open orders")
            
        for order in open_orders:
            try:
                # Cancel multiple orders at once
                response = self.client.futures_cancel_order(symbol=op_symbol, orderId=order['orderId'])
                logging.debug(f"Order to cancel: {order}")
                logging.debug(f"Binance response to cancel: {response}")
                print(str(response['type']) + " Price: " + str(response['price']) + " Quantity: " + str(response['origQty']) + " ❌")
            except Exception as e:
                logging.exception(f"Error cancelling orders: {e} ")
                print(f"Error cancelling orders: {e} ")

        # Clear grid_body after all cancellations
        print("All grid orders cancelled and cleared.")
    

    def update_current_position(self):
        
        logging.info("UPDATING CURRENT POSITION...")
        
        try:
            # Fetch futures position information
            response = self.client.futures_position_information(symbol=self.data_grid['symbol'])
            

            # Loop through the list to find the relevant position based on 'positionSide'
            for position_info in response:
                if float(position_info['positionAmt']) != 0:  # Skip empty positions if the exchange is in hedge mode the response 2 current position, one is 0
                    self.data_grid['current_line']['price'] = float(position_info.get('entryPrice', 0))
                    self.data_grid['current_line']['quantity'] = float(position_info.get('positionAmt', 0))
                    self.data_grid['current_line']['position_side'] = position_info.get('positionSide', 'UNKNOWN')
                    
                    logging.debug(f"Current position from Binance: {position_info}")
                    logging.debug(f"Current position on current_line: {self.data_grid['current_line']}")
                    
                    break  # Exit after finding the first non-empty position

        except Exception as e:
            logging.exception(f"update_current_position | Error fetching position information for {self.data_grid['symbol']}: {e}")
            # Log or handle the error in case the API call fails
            print(f"update_current_position | Error fetching position information for {self.data_grid['symbol']}: {e}")

            
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


    







