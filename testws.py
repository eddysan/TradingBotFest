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
                    grid.write_data_grid()
                
            case "GD": #the event taken is in grid
                    print(f"GD grid.: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    grid.update_current_position() #read current position
                    grid.clean_ul_order()
                    grid.post_ul_order()
                    grid.write_data_grid() # saving all configuration to json
                                                        
            case "UL": #the event is unload
                    print(f"UNLOAD operation: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    grid.update_current_position() #read current position
                    grid.clean_ul_order() # clean unload existing position
                    grid.clean_grid_order() # clean grid rest orders
                    grid.clean_tp_order() # clean take profit order
                    grid.clean_sl_order() # clean stop loss order
                    grid.update_entry_line() # updating entry line from current_line values
                    grid.post_grid_order() # generate new grid and post it, taking entry price as entry and post it
                    grid.post_sl_order() # post stop loss order
                    grid.post_tp_order() # post take profit order
                    grid.write_data_grid() # saving all configuration to json
                
            case "SL": #the event is stop loss
                    print(f"STOP_LOSS operation, {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    # close all open orders from list grid
                
            case "TP": #the event is take profit
                    print(f"TAKE_PROFIT operation: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    # close all open orders from grid list
                    
            case _:
                    print(f"No kind operation")
            

