import json
from binance.client import Client
from binance.streams import BinanceSocketManager
from websocket import WebSocketApp
import time
from model import *

ws = None  # Global variable for WebSocket connection

client = get_connection()

cfile = "message.json"
with open(cfile, 'r') as file:
    message = json.load(file)
    
    
#    message = json.loads(message) #message received

if message.get('e') == 'ORDER_TRADE_UPDATE' and message['o']['X'] == 'FILLED':
    symbol = message['o']['s']  # Symbol (e.g., XRPUSDT)
    #order_status = message['o']['X']  # Order status (e.g., FILLED, NEW)
    order_id = message['o']['i']  # Order ID
    kind_order = str(message['o']['c'])[:2] #getting kind of operation on grid (GD, TP, SL, IN, UL etc)
    operation_code = str(message['o']['c']).split('_')[1] # getting operation code
    
    grid = LUGrid(operation_code)
        
        
    # Filter for SYMBOL pair and when order is filled
    if symbol == grid.symbol:
            
        match kind_order:
            case "IN": #the event is entry
                    print(f"IN: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    grid.update_current_position() # read position information at first the position will be same as entry_line
                    grid.save_config() # saving all configuration to json
                
            case "GD": #the event taken is in grid
                    print(f"GD grid.: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    grid.update_current_position() #read current position
                    
                    # get the current position
                    # calculate unload price and quantity
                    # delete existing unload order
                    # post unload
                    grid.save_config() # saving all configuration to json
                    
                                    
            case "UL": #the event is unload
                    print(f"UNLOAD operation: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    grid.update_current_position() #read current position
                    # delete all open orders (grid, tp, sl)
                    # read and load new entry point: price and quantity
                    # generate new grid with new entry
                    # post grid
                    # post SL
                    # post TP
                    grid.save_config() # saving all configuration to json
                
            case "SL": #the event is stop loss
                    print(f"STOP_LOSS operation, {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    # close all open orders from list grid
                
            case "TP": #the event is take profit
                    print(f"TAKE_PROFIT operation: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    # close all open orders from grid list
                    
            case _:
                    print(f"No kind operation")
            

