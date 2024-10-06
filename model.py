#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import json
from binance.client import Client
import time
import math

# prompt to get data
def get_external_data(data_grid):    

    # try input and apply default values
    data_grid['symbol'] = input("Token Pair (BTCUSDT): ").upper() + "USDT"
    data_grid['grid_side'] = str(input("Grid Side (long): ")).upper() or 'LONG'
    data_grid['grid_distance'] = float(input("Grid Distance (2%): ") or 2) / 100
    data_grid['quantity_increment'] = float(input("Token Increment (40%): ") or 40) / 100
    data_grid['sl_amount'] = float(input("Stop Loss Amount ($10): ") or 10.0)
    data_grid['entry_price'] = float(input("Entry Price: ") or 0.00000)
    data_grid['entry_quantity'] = float(input("Entry Quantity ($10): ") or 0.00000)
    data_grid['entry_quantity'] = data_grid['entry_quantity'] / data_grid['entry_price']

    return data_grid


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
    
    def __init__(self, data_grid):
        # initial default values
        self.symbol = data_grid['symbol']
        self.compound = data_grid['compound']
        self.unload_distance = data_grid['ul_distance']
        self.price_precision = 0 # number of decimals places after point
        self.quantity_precision = 0 # number of decimals places after point
        self.tick_size = 0 #increment between points in price, setted by binance
        self.step_size = 0
        
        # initiate client connection for entire operations on this class
        self.client = get_connection()
        self.get_quantity_precision()
        
    
    
    # round price to increment accepted by binance
    def round_to_tick_size(self, price):
        tick_increment = int(abs(math.log10(self.tick_size)))
        return round(price, tick_increment)
    
    # get decimal precision for price and quantity 
    def get_quantity_precision(self):    
        while True:
            try:
                info = self.client.futures_exchange_info()['symbols']
                break  # Exit loop if successful
            except Exception as error:
                print(error)
                with open("log.txt", "a") as archivo_e:
                    mensaje_e = time.strftime('%d-%m-%Y %H:%M:%S', time.localtime()) + ' ERROR: ' + str(error) + "\n"
                    archivo_e.write(mensaje_e)
                time.sleep(2)  # Retry after delay

        # Find the symbol's info using filter() or next() for better performance
        symbol_info = next((x for x in info if x['symbol'] == self.symbol), None)
    
        if not symbol_info:
            return None  # Return None if symbol is not found
    
        for f in symbol_info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                self.step_size = float(f['stepSize'])
            if f['filterType'] == 'PRICE_FILTER':
                self.tick_size = float(f['tickSize'])
        
        self.price_precision = symbol_info['pricePrecision']
        self.quantity_precision = symbol_info['quantityPrecision']
        
        return None
    
    
    # load data as json in order to set default config
    def load_data(self,data_grid):
        self.symbol = data_grid['symbol'].upper() # symbol pair like BTCUSDT
        self.side = data_grid['grid_side'].upper() # side LONG or SHORT
        self.grid_distance = round(data_grid['grid_distance'], 2)  # distance between lines in grid, by default 2% then 0.02
        self.quantity_increment = round(data_grid['quantity_increment'], 2) #increment for token quantity, by default 40%
        self.stop_loss_amount = round(data_grid['sl_amount'], 2) #amount to lose if stop loss is activated
        
        self.entry_line = {"entry": "IN", 
                           "side": 'BUY' if self.side.upper() == 'LONG' else 'SELL',
                           "position_side": self.side.upper(),
                           "price": self.round_to_tick_size(data_grid['entry_price']), 
                           "quantity": round(data_grid['entry_quantity'], self.quantity_precision), 
                           "cost":  round(data_grid['entry_price'] * data_grid['entry_quantity'], 2)
                           }
        self.take_profit_line = {"entry": "TP",
                                 "side": 'SELL' if self.side == 'LONG' else 'BUY', #if the operation is LONG then the TP should be SELL and viceversa
                                 "position_side": self.side.upper(), #mandatory for hedge mode
                                 "distance": data_grid['tp_distance'], #percentage distance for take profit
                                 "price": 0.00, 
                                 "quantity": 0.00, 
                                 "cost": 0.00
                                 }        
        self.unload_line = {"entry": "UL", 
                            "distance": data_grid['ul_distance'], 
                            "price": 0.00, 
                            "quantity": 0.00, 
                            "cost": 0.00
                            }
        self.grid_body = []
        self.average_line = {}

        self.stop_loss_line = {"entry": "SL", 
                               "side": 'SELL' if self.side == 'LONG' else 'BUY', #if the operation is LONG then the SL should be SELL
                               "position_side": self.side.upper(), #mandatory for hedge mode
                               "distance": 0.00, #stop loss percentage distance
                               "price": 0.00, 
                               "quantity": 0.00, 
                               "cost": 0.00
                               }
    
    # generate the entire grid
    def generate_grid(self):
        current_price = self.entry_line["price"]
        current_quantity = self.entry_line["quantity"]
        
        self.average_line['price'] = self.entry_line["price"]
        self.average_line['quantity'] = self.entry_line["quantity"]

        # set stop loss taking the first point, entry line
        self.average_line['sl_distance'] = (self.stop_loss_amount * 100) / (self.average_line['price'] *  self.average_line['quantity'])
        
        if self.side == 'LONG':
            self.stop_loss_line['price'] = self.round_to_tick_size( self.average_line['price'] - (self.average_line['price'] * self.average_line['sl_distance'] / 100) )
            self.stop_loss_line['distance'] = round((self.entry_line['price'] - self.stop_loss_line['price']) / self.entry_line['price'],4)
            
        if self.side == 'SHORT':
                self.stop_loss_line['price'] = self.round_to_tick_size( self.average_line['price'] + (self.average_line['price'] * self.average_line['sl_distance'] / 100) )
                self.stop_loss_line['distance'] = round((self.stop_loss_line['price'] - self.entry_line['price']) / self.entry_line['price'],4)

        while True:
            
            # increment as grid distance the price and quantity
            if self.side == 'LONG':
                new_price = current_price * (1 - self.grid_distance)
            
            if self.side == 'SHORT':
                new_price = current_price * (1 + self.grid_distance)
            
            new_quantity = current_quantity * (1 + self.quantity_increment)
            
            # control if the new price is greater or lower than stop loss price, in order to stop generation of posts
            if self.side == 'LONG':
                if self.stop_loss_line['price'] > new_price:
                    break
                
            if self.side == 'SHORT':
                if new_price > self.stop_loss_line['price']:
                    break
            
            self.grid_body.append({"entry" : len(self.grid_body)+1,
                                   "side": 'BUY' if self.side.upper() == 'LONG' else 'SELL',
                                   "position_side": self.side.upper(),
                                   "price" : self.round_to_tick_size(new_price), 
                                   "quantity" : round(new_quantity, self.quantity_precision), 
                                   "cost" : round(new_price * new_quantity, 2)
                                   })
            
            # calculate the average price and accumulated quantity if the position is taken
            self.average_line['price'] = self.round_to_tick_size( ((self.average_line['price'] * self.average_line['quantity']) + (new_price * new_quantity)) / (self.average_line['quantity'] + new_quantity)) 
            self.average_line['quantity'] = round(self.average_line['quantity'] + new_quantity, self.quantity_precision)
            
            self.average_line['sl_distance'] = (self.stop_loss_amount * 100) / (self.average_line['price'] *  self.average_line['quantity'])
            
            if self.side == 'LONG':
                self.stop_loss_line['price'] = self.round_to_tick_size( self.average_line['price'] - (self.average_line['price'] * self.average_line['sl_distance'] / 100) )
                self.stop_loss_line['distance'] = round((self.entry_line['price'] - self.stop_loss_line['price']) / self.entry_line['price'],4)
            
            if self.side == 'SHORT':
                self.stop_loss_line['price'] = self.round_to_tick_size( self.average_line['price'] + (self.average_line['price'] * self.average_line['sl_distance'] / 100) )
                self.stop_loss_line['distance'] = round((self.stop_loss_line['price'] - self.entry_line['price']) / self.entry_line['price'],4)

            
            current_price = new_price
            current_quantity = new_quantity
        
        # generate TAKE PROFIT line
        if self.side.upper() == 'LONG':
            self.take_profit_line['price'] = self.round_to_tick_size( self.entry_line['price'] * (1 + self.take_profit_line['distance']) )
        else:
            self.take_profit_line['price'] = self.round_to_tick_size( self.entry_line['price'] * (1 - self.take_profit_line['distance']) )
    
            
    # generate unload point
    def generate_unload(self):
        if self.side.upper() == 'LONG':
            self.unload_line['price'] = self.round_to_tick_size( self.entry_line['price'] * (1 + self.unload_line['distance']) )
        else:
            self.unload_line['price'] = self.round_to_tick_size( self.entry_line['price'] * (1 - self.unload_line['distance']) )
        return None
    
    
    # post entry order
    def post_entry_order(self):
        try:
            # Ensuring entry_line contains necessary keys
            if all(k in self.entry_line for k in ['price', 'quantity']):
                response = self.client.futures_create_order(
                    symbol = self.symbol.upper(),
                    side = self.entry_line['side'],
                    type = 'LIMIT',
                    timeInForce = 'GTC',
                    positionSide = self.entry_line['position_side'],
                    price = self.entry_line['price'],
                    quantity = self.entry_line['quantity']
                    )
                print(f"{self.entry_line['entry']} | {self.entry_line['price']} | "
                  f"{self.entry_line['quantity']} | {self.entry_line['cost']} --> ok")
            else:
                print("Error: entry_line missing required fields.")
        except Exception as e:
            print(f"Error placing order: {e}")        
        
        return None
    
    
    # post a limit order for grid body
    def post_grid_order(self):
        try:
            for i in range(len(self.grid_body)):
                response = self.client.futures_create_order(
                    symbol = self.symbol.upper(),
                    side = self.grid_body[i]['side'],
                    type = 'LIMIT',
                    timeInForce = 'GTC',
                    positionSide = self.grid_body[i]['position_side'],
                    price = self.grid_body[i]['price'],  
                    quantity = self.grid_body[i]['quantity'] 
                    )
                
                print(f"{self.grid_body[i]['entry']} | {self.grid_body[i]['price']} | {self.grid_body[i]['quantity']} | {self.grid_body[i]['cost']} --> ok")
                
        except KeyError as e:
            print(f"Missing key in order data: {e}")
        except Exception as e:
            print(f"Error posting order: {e}")
    
       
    # post entry order
    def post_sl_order(self):
        try:
            response = self.client.futures_create_order(
                    symbol = self.symbol.upper(),
                    side = self.stop_loss_line['side'], #if the operation is LONG then the SL should be SELL
                    positionSide = self.stop_loss_line['position_side'],
                    type = 'STOP_MARKET',
                    stopPrice = self.stop_loss_line['price'],
                    closePosition = True
                    )
            print(f"{self.stop_loss_line['entry']}(self.stop_loss_line['distance']%)  | {self.stop_loss_line['price']} | "
                  f"{self.stop_loss_line['quantity']} | {self.stop_loss_line['cost']} --> ok")
        except Exception as e:
            print(f"Error placing order: {e}")        
        
        return None


    # post entry order
    def post_tp_order(self):
        try:
            response = self.client.futures_create_order(
                    symbol = self.symbol.upper(),
                    side = self.take_profit_line['side'], #if the operation is LONG then the TP should be SELL
                    positionSide = self.take_profit_line['position_side'],
                    type = 'TAKE_PROFIT_MARKET',
                    stopPrice = self.take_profit_line['price'],
                    closePosition = True
                    )
            print(f"{self.take_profit_line['entry']}(self.take_profit_line['distance']%)  | {self.take_profit_line['price']} | "
                  f"{self.take_profit_line['quantity']} | {self.take_profit_line['cost']} --> ok")
        except Exception as e:
            print(f"Error placing order: {e}")        
        
        return None



    
    
    def print_grid(self):
        try:
            # Print entry line
            print(f"{self.entry_line['entry']} | {self.entry_line['price']} | {self.entry_line['quantity']} | {self.entry_line['cost']}")

            # Print grid body
            for line in self.grid_body:
                print(f"{line['entry']} | {line['price']} | {line['quantity']} | {line['cost']}")

            # Print stop loss line
            print(f"{self.stop_loss_line['entry']} ({self.stop_loss_line['distance'] * 100:.2f}%) | "
              f"{self.stop_loss_line['price']} | {self.stop_loss_line['quantity']} | "
              f"{self.stop_loss_line['cost']}")
    
        except KeyError as e:
            print(f"Missing key in data: {e}")
        except Exception as e:
            print(f"Error while printing grid: {e}")


    







