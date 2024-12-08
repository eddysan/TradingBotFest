from datetime import datetime
import os
import uuid
import json
from binance.client import Client
import math
import logging
import time
from package_common import *
from package_clean import *


# input data from console
def input_data():
    logging.debug(f"INPUT DATA...")
    
    client = get_connection()  # Open Binance connection

    # INPUT symbol
    symbol = input("Symbol (BTC): ").upper() + "USDT"

    if os.path.exists(f"ops/{symbol}.json"):
        config = read_config_data(f"ops/{symbol}.json")
    else:
        config = read_config_data(f"config/theloadunload.config")

    config['symbol'] = symbol

    # INPUT position side (default to LONG)
    config['input_side'] = input("Side (LONG): ").upper() or 'LONG'

    # Fetch info if there is a current position
    response = client.futures_position_information(symbol=config['symbol'])

    # Loop through the list to find the relevant position based on 'positionSide'
    for position_info in response:
        if float(position_info['positionAmt']) != 0 and position_info['positionSide'] == config['position_side']:  # if position amount is not zero, then there is a current position
            print(f"There is a current position... \n"
                f"Position side: {position_info['positionSide']} \n"
                f"Price: {position_info['entryPrice']} \n"
                f"Quantity: {abs(position_info['positionAmt'])}")
            config[config['input_side']]['entry_line']['price'] = float(position_info['entryPrice'])
            config[config['input_side']]['entry_line']['quantity'] = abs(float(position_info['positionAmt']))
            config[config['input_side']]['entry_line']['status'] = 'FILLED'


    # getting wallet current balance
    config['wallet_balance_usdt'] = round(next((float(b['balance']) for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0), 2)
    config['risk_amount'] = round(float(config['wallet_balance_usdt']) * (config['risk']/100), 2)

    # Getting precisions for the symbol
    info = client.futures_exchange_info()['symbols']
    symbol_info = next((x for x in info if x['symbol'] == symbol), None)
    
    # Retrieve precision filter 
    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            config['step_size'] = float(f['stepSize'])
        elif f['filterType'] == 'PRICE_FILTER':
            config['tick_size'] = float(f['tickSize'])
    
    config['price_precision'] = symbol_info['pricePrecision']
    config['quantity_precision'] = symbol_info['quantityPrecision']

    if config[config['input_side']]['entry_line']['status'] != 'FILLED':
        #INPUT entry price
        tick_increment = int(abs(math.log10(config['tick_size'])))
        input_price = float(input("Entry Price ($): ") or 0)
        config[config['input_side']]['entry_line']['price'] = round(input_price, tick_increment)
        #INPUT quantity
        entry_q = input(f"Entry Quantity ({config['risk_amount']}$): ") or config['risk_amount']  # getting quantity in USDT
        config[config['input_side']]['entry_line']['quantity'] = round(float(entry_q) / config[config['input_side']]['entry_line']['price'], config['quantity_precision'])  # converting USDT entry to tokens
        config[config['input_side']]['entry_line']['status'] = 'NEW'

    # INPUT grid distance
    config[config['input_side']]['grid_distance'] = float(input("Grid Distance (2%): ") or 2) # default valur for grid distance is 2%

    # INPUT token increment
    config[config['input_side']]['quantity_increment'] = float(input("Token Increment (40%): ") or 40) # default increment is 40%

    # INPUT stop_loss_amount
    config[config['input_side']]['stop_loss_amount'] = float(input(f"Stop Loss Amount ({config['risk_amount']}$): ") or config['risk_amount'])

    # saving to data grid
    write_config_data('ops', f"{config['symbol']}.json", config)
        
    return config['symbol']


class LUGrid:
    def __init__(self, symbol):
        self.symbol = symbol # operation code
        self.data_grid = read_config_data(f"ops/{symbol}.json") #reading configuration files
        self.client = get_connection() #new connection


    def post_order(self):
        self.side = self.data_grid['input_side']
        self.in_line = self.data_grid[self.side]['entry_line']
        self.ul_line = self.data_grid[self.side]['unload_line']
        self.tp_line = self.data_grid[self.side]['take_profit_line']
        self.sl_line = self.data_grid[self.side]['stop_loss_line']
        self.hd_line = self.data_grid[self.side]['hedge_line']
        self.av_line = self.data_grid[self.side]['average_line']
        self.cr_line = self.data_grid[self.side]['current_line']
        self.bd_line = self.data_grid[self.side]['body_line']
        self.sl_amount = self.data_grid[self.side]['stop_loss_amount']
        self.gd_distance = self.data_grid[self.side]['grid_distance']
        self.qt_increment = self.data_grid[self.side]['quantity_increment']

        self.generate_grid()
        if self.in_line['status'] != 'FILLED':
            self.post_entry_order()
        self.post_grid_order()
        self.post_sl_order()
        if self.tp_line['enabled']:
            self.generate_take_profit()
            self.post_tp_order()

        self.write_data_grid()


    def attend_message(self, message):
        self.side = message['o']['ps']
        self.in_line = self.data_grid[self.side]['entry_line']
        self.ul_line = self.data_grid[self.side]['unload_line']
        self.tp_line = self.data_grid[self.side]['take_profit_line']
        self.sl_line = self.data_grid[self.side]['stop_loss_line']
        self.av_line = self.data_grid[self.side]['average_line']
        self.cr_line = self.data_grid[self.side]['current_line']
        self.bd_line = self.data_grid[self.side]['body_line']
        self.sl_amount = self.data_grid[self.side]['stop_loss_amount']
        self.gd_distance = self.data_grid[self.side]['grid_distance']
        self.qt_increment = self.data_grid[self.side]['quantity_increment']

        transaction_type = self.get_transaction_type(message)

        match transaction_type:
            case "GRID":  # the event taken is in grid including entry transaction
                logging.info(f"{message['o']['s']}_{message['o']['ps']} Order taken: Price: {message['o']['p']}, Quantity: {message['o']['q']}")
                self.update_current_position()  # read position information at first the position will be same as entry_line

                if self.ul_line['enabled']:
                    clean_order(self.symbol, self.in_line['position_side'], 'UL')  # clean unload order if there is an unload order opened
                    self.generate_unload_order()
                    self.post_ul_order()

                if self.tp_line['enabled']:
                    clean_order(self.symbol, self.in_line['position_side'], 'TP')
                    self.generate_take_profit()
                    self.post_tp_order()  # when an entry line is taken, then take profit will be posted

                self.write_data_grid()

            case "UNLOAD":  # the event is unload
                logging.info(f"{self.symbol}_{self.side} UL order: price: {message['o']['p']}, quantity: {message['o']['q']}")

                clean_open_orders(self.symbol, self.in_line['position_side'])  # clean all order for the position side
                self.update_current_position()  # read current position
                self.update_entry_line()  # updating entry line from current_line values
                self.generate_grid()  # generate new grid points
                self.post_sl_order()  # post stop loss order
                self.post_grid_order()  # generate new grid and post it, taking entry price as entry and post it
                if self.tp_line['enabled']:
                    self.generate_take_profit()
                    self.post_tp_order()  # when an entry line is taken, then take profit will be posted

                self.write_data_grid()

            case "STOP_LOSS":  # the event is stop loss
                logging.info(f"{self.symbol}_{self.in_line['position_side']} SL order: price: {message['o']['p']}, quantity: {message['o']['q']}")
                clean_open_orders(self.symbol, self.in_line['position_side'])  # clean all order for the position side
                # close all open orders from list grid

            case "TAKE_PROFIT":  # the event is take profit
                logging.info(f"{self.symbol}_{self.in_line['position_side']} TP order: price: {message['o']['p']}, quantity: {message['o']['q']}")
                clean_open_orders(self.symbol, self.in_line['position_side'])  # clean all order for the position side
                # close all open orders from grid list

            case _:
                logging.warning(f"{self.symbol}_{self.in_line['position_side']} No matching operation for {self.symbol}")
                print(f"No kind operation")

    # get transaction type
    def get_transaction_type(self, message):
        transaction_type = 'NONE'
        if message['o']['o'] == 'LIMIT':
            if message['o']['ps'] == 'LONG' and message['o']['S'] == 'BUY':
                transaction_type = 'GRID'

            if message['o']['ps'] == 'LONG' and message['o']['S'] == 'SELL':
                transaction_type = 'UNLOAD'

            if message['o']['ps'] == 'SHORT' and message['o']['S'] == 'SELL':
                transaction_type = 'GRID'

            if message['o']['ps'] == 'SHORT' and message['o']['S'] == 'BUY':
                transaction_type = 'UNLOAD'

        if message['o']['o'] == 'TAKE_PROFIT_MARKET':
            transaction_type = 'TAKE_PROFIT'

        if message['o']['o'] == 'STOP_MARKET':
            transaction_type = 'STOP_LOSS'

        return transaction_type

    
    # round price to increment accepted by binance
    def round_to_tick_size(self, price):
        tick_increment = int(abs(math.log10(self.data_grid['tick_size'])))
        return round(price, tick_increment)
    
    # generate the entire grid points, stop loss and take profit
    def generate_grid(self):
        logging.debug(f"{self.symbol} GENERATING DATA_GRID LINES...")
        self.bd_line = [] # clean bd line first
        # current line is the pivot that store que current price in operation, this will change if the grid has chaged
        self.cr_line['price'] = self.in_line['price']
        self.cr_line['quantity'] = self.in_line['quantity']
        self.cr_line['position_side'] = self.in_line['position_side']
        
        self.data_grid['body_line'] = [] #cleaning grid body before operations
        current_price = self.in_line["price"]
        current_quantity = self.in_line["quantity"]
        
        self.av_line['price'] = self.in_line["price"]
        self.av_line['quantity'] = self.in_line["quantity"]

        # set stop loss taking the first point, entry line
        self.av_line['sl_distance'] = (self.sl_amount * 100) / (self.av_line['price'] *  self.av_line['quantity'])
        
        if self.side == 'LONG':
            self.sl_line['price'] = self.round_to_tick_size( self.av_line['price'] - (self.av_line['price'] * self.av_line['sl_distance'] / 100) )
            self.sl_line['distance'] = round((self.in_line['price'] - self.sl_line['price']) / self.in_line['price'],4)
            
        if self.side == 'SHORT':
                self.sl_line['price'] = self.round_to_tick_size( self.av_line['price'] + (self.av_line['price'] * self.av_line['sl_distance'] / 100) )
                self.sl_line['distance'] = round((self.sl_line['price'] - self.in_line['price']) / self.in_line['price'],4)

        self.sl_line['quantity'] = self.in_line['quantity']
        self.sl_line['cost'] = self.in_line['cost']

        while True:
            # increment as grid distance the price and quantity
            if self.side == 'LONG':
                new_price = current_price * (1 - (self.gd_distance / 100))
            
            if self.side == 'SHORT':
                new_price = current_price * (1 + (self.gd_distance / 100))
            
            new_quantity = current_quantity * (1 + (self.qt_increment / 100))
            
            # control if the new price is greater or lower than stop loss price, in order to stop generation of posts
            if self.side == 'LONG':
                if self.sl_line['price'] > new_price:
                    break
                
            if self.side == 'SHORT':
                if new_price > self.sl_line['price']:
                    break
            
            self.bd_line.append({"label" : len(self.bd_line)+1,
                                   "side": 'BUY' if self.side == 'LONG' else 'SELL',
                                   "position_side": self.side,
                                   "price" : self.round_to_tick_size(new_price), 
                                   "quantity" : round(new_quantity, self.data_grid['quantity_precision']),
                                   "type": "LIMIT",
                                   "cost" : round(new_price * new_quantity, 2),
                                   })
            
            
            # calculate the average price and accumulated quantity if the position is taken
            self.av_line['price'] = self.round_to_tick_size( ((self.av_line['price'] * self.av_line['quantity']) + (new_price * new_quantity)) / (self.av_line['quantity'] + new_quantity))
            self.av_line['quantity'] = round(self.av_line['quantity'] + new_quantity, self.data_grid['quantity_precision'])
            
            self.av_line['sl_distance'] = (self.sl_amount * 100) / (self.av_line['price'] *  self.av_line['quantity'])
            
            if self.side == 'LONG':
                self.sl_line['price'] = self.round_to_tick_size( self.av_line['price'] - (self.av_line['price'] * self.av_line['sl_distance'] / 100) )
                self.sl_line['distance'] = round((self.in_line['price'] - self.sl_line['price']) / self.in_line['price'],4)
            
            if self.side == 'SHORT':
                self.sl_line['price'] = self.round_to_tick_size( self.av_line['price'] + (self.av_line['price'] * self.av_line['sl_distance'] / 100) )
                self.sl_line['distance'] = round((self.sl_line['price'] - self.in_line['price']) / self.in_line['price'],4)

            self.sl_line['quantity'] = round(self.sl_line['quantity'] + new_quantity, self.data_grid['quantity_precision'])
            self.sl_line['cost'] = round(self.sl_line['cost'] + (new_price * new_quantity), 2)
            
            current_price = new_price
            current_quantity = new_quantity
            
        logging.debug(f"{self.symbol} body_line generated: {self.bd_line}")
        logging.debug(f"{self.symbol} stop_loss_line generated: {self.sl_line}")


    # Calculate the take profit price based on the side
    def generate_take_profit(self):
        price_factor = 1 + (self.tp_line['distance']/100) if self.in_line['position_side'] == 'LONG' else 1 - (self.tp_line['distance']/100)
        self.tp_line['price'] = self.round_to_tick_size(self.in_line['price'] * price_factor)
        logging.debug(f"{self.symbol} take_profit_line generated: {self.tp_line}")

    # update entry line data taking current line as data, and the current position will be the new entry
    def update_entry_line(self):
        logging.debug(f"{self.symbol} UPDATING ENTRY_LINE FROM CURRENT_LINE...")
    
        # Update entry line with current line values
        self.in_line['price'] = self.cr_line['price']
        self.in_line['quantity'] = self.cr_line['quantity']
        self.in_line['cost'] = round(self.in_line['price'] * self.in_line['quantity'], 2)
        
        logging.debug(f"{self.symbol} current_line: {self.cr_line}")
        logging.debug(f"{self.symbol} entry_line updated: {self.in_line}")
        
        return None
    
    
    # post entry order
    def post_entry_order(self):
        logging.debug(f"{self.symbol} POSTING ENTRY ORDER TO BINANCE...")
    
        try:
            # Create the entry order
            response = self.client.futures_create_order(
                symbol = self.symbol,
                side = self.in_line['side'],
                type = self.in_line['type'],
                timeInForce = 'GTC',
                positionSide = self.in_line['position_side'],
                price = self.in_line['price'],
                quantity = self.in_line['quantity']
            )

            # Log the placed order details
            logging.debug(f"{self.symbol} Binance response: {response}")
            logging.info(f"{self.symbol} - {self.in_line['label']} | {self.in_line['price']} | {self.in_line['quantity']} | {self.in_line['cost']} ...POSTED")

        except Exception as e:
            logging.exception(f"{self.symbol} Error placing entry_line order: {self.in_line} \n {e}")

        return None

            
    # post a limit order for grid body
    def post_grid_order(self):
        logging.debug(f"{self.symbol} POSTING BODY LINE...")
        try:
            for i in range(len(self.bd_line)):
                response = self.client.futures_create_order(
                    symbol = self.symbol,
                    side = self.bd_line[i]['side'],
                    type = self.bd_line[i]['type'],
                    timeInForce = 'GTC',
                    positionSide = self.bd_line[i]['position_side'],
                    price = self.bd_line[i]['price'],
                    quantity = self.bd_line[i]['quantity']
                    )

                logging.debug(f"{self.symbol} Binance response: {response}")
                logging.info(f"{self.symbol} - {self.bd_line[i]['label']} | {self.bd_line[i]['price']} | {self.bd_line[i]['quantity']} | {self.bd_line[i]['cost']} ...POSTED")
                
        except KeyError as e:
            logging.exception(f"{self.symbol} Posting grid orders: Missing key in order data: {e}")
        except Exception as e:
            logging.exception(f"Error posting grid data: {e}")

    # post entry order
    def post_sl_order(self):
        logging.debug(f"{self.symbol} POSTING STOP_LOSS ORDER...")
        try:
            # Post the stop loss order
            response = self.client.futures_create_order(
                symbol = self.symbol,
                side = self.sl_line['side'],  # SL for LONG is SELL and vice versa
                positionSide = self.sl_line['position_side'],
                type = self.sl_line['type'],
                stopPrice = self.sl_line['price'],
                closePosition = True
            )

            # Log the placed order details
            logging.debug(f"{self.symbol} stop_loss_line binance response: {response}")
            
            # Log successful stop loss order
            logging.info(f"{self.symbol} - {self.sl_line['label']} ({round(self.sl_line['distance']*100, 2)}%) | "
                  f"{self.sl_line['price']} | {self.sl_line['quantity']} | "
                  f"{self.sl_line['cost']} ...POSTED")

        except Exception as e:
            logging.exception(f"{self.symbol} Error placing stop loss order: {e}")



    # post take profit order
    def post_tp_order(self):
        logging.debug(f"{self.symbol} POSTING TAKE PROFIT ORDER...")
        try:
            # Post the take profit order
            response = self.client.futures_create_order(
                symbol=self.symbol,
                side=self.tp_line['side'],  #TP for LONG is SELL and vice versa
                positionSide=self.tp_line['position_side'],
                type=self.tp_line['type'],
                stopPrice=self.tp_line['price'],
                closePosition=True
            )

            # Log the placed order details
            logging.debug(f"{self.symbol} take_profit_line binance response: {response}")
            
            # Log the successful order
            logging.info(f"{self.symbol} - {self.tp_line['label']} ({round(self.tp_line['distance'],2)}%) | "
                  f"{self.tp_line['price']} | {self.tp_line['quantity']} | "
                  f"{self.tp_line['cost']} ...POSTED")
            
        except Exception as e:
            logging.exception(f"{self.symbol} Error placing take profit order: {e}")

    # generate unload order
    def generate_unload_order(self):
        # Calculate the unload price based on the side (LONG or SHORT)
        price_factor = 1 + (self.ul_line['distance']/100) if self.in_line['position_side'] == 'LONG' else 1 - (self.ul_line['distance']/100)
        self.ul_line['price'] = self.round_to_tick_size(self.cr_line['price'] * price_factor)

        # Calculate unload quantity
        self.ul_line['quantity'] = round(
            self.cr_line['quantity'] - self.in_line['quantity'],  # always take the original quantity inserted
            self.data_grid['quantity_precision']
        )

        logging.debug(f"{self.symbol} unload_line generated: {self.ul_line}")

    # post unload order
    def post_ul_order(self):
        logging.debug(f"{self.symbol} POSTING UNLOAD ORDER...")
        if float(self.ul_line['quantity']) == 0:
            logging.debug(f"{self.symbol} Can't post unload because zero quantity")
            return

        try:
            # Post the limit order
            response = self.client.futures_create_order(
                symbol=self.symbol,
                side=self.ul_line['side'],
                type=self.ul_line['type'],
                timeInForce='GTC',
                positionSide=self.ul_line['position_side'],
                price=self.ul_line['price'],
                quantity=self.ul_line['quantity']
            )

            logging.debug(f"{self.symbol} unload_line response from binance: {response}")
            
            # Log the success message
            logging.info(f"{self.symbol} - {self.ul_line['label']} | "
                  f"{self.ul_line['price']} | {self.ul_line['quantity']} ...POSTED")
        
        except Exception as e:
            logging.exception(f"{self.symbol} Error posting Unload order: {e}")

    # update current position into current line
    def update_current_position(self):
        
        logging.debug(f"{self.symbol} UPDATING CURRENT POSITION...")
        
        try:
            # Fetch futures position information
            response = self.client.futures_position_information(symbol=self.symbol)

            # Loop through the list to find the relevant position based on 'positionSide'
            for position_info in response:
                if float(position_info['positionAmt']) != 0:  # Skip empty positions if the exchange is in hedge mode the response 2 current position, one is 0
                    self.cr_line['price'] = float(position_info['entryPrice'])
                    self.cr_line['quantity'] = abs(float(position_info['positionAmt']))
                    self.cr_line['position_side'] = position_info['positionSide']
                    logging.debug(f"{self.symbol} Current position from Binance: {position_info}")
                    break  # Exit after finding the first non-empty position
        except Exception as e:
            logging.exception(f"{self.symbol} update_current_position | Error fetching position information: {e}")


    def write_data_grid(self):
        self.data_grid[self.side]['entry_line'] = self.in_line
        self.data_grid[self.side]['unload_line'] = self.ul_line
        self.data_grid[self.side]['take_profit_line'] = self.tp_line
        self.data_grid[self.side]['stop_loss_line'] = self.sl_line
        self.data_grid[self.side]['average_line'] = self.av_line
        self.data_grid[self.side]['current_line'] = self.cr_line
        self.data_grid[self.side]['body_line'] = self.bd_line
        self.data_grid[self.side]['stop_loss_amount'] = self.sl_amount
        self.data_grid[self.side]['grid_distance'] = self.gd_distance
        self.data_grid[self.side]['quantity_increment'] = self.qt_increment

        write_config_data('ops', f"{self.symbol}.json", self.data_grid)

