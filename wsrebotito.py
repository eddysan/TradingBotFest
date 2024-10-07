#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
from binance.client import Client
from binance.streams import BinanceSocketManager
from websocket import WebSocketApp
import time
from model import *

# if compound is true then quantity will be taken as 10% of entire capital
data_grid = {"compound": False,
             "tp_distance": 0.05,
             "ul_distance": 0.005
    }


#data_grid = get_external_data(data_grid)

# default variables to dev
data_grid['symbol'] = 'ADAUSDT'
data_grid['grid_side'] = 'LONG'
data_grid['grid_distance'] = 0.02
data_grid['quantity_increment'] = 0.40
data_grid['sl_amount'] = 10
data_grid['entry_price'] = 0.345
data_grid['entry_quantity'] = 28

grid = LUGrid(data_grid)

grid.load_data(data_grid)
grid.generate_grid()
#grid.generate_unload()

grid.post_entry_order()
grid.post_grid_order()
grid.post_sl_order()
grid.post_tp_order()
#grid.print_grid()

client = get_connection()


ws = None  # Global variable for WebSocket connection

def on_message(ws, message):

    message = json.loads(message) #message received

    if message.get('e') == 'ORDER_TRADE_UPDATE':
        symbol = message['o']['s']  # Symbol (e.g., XRPUSDT)
        order_status = message['o']['X']  # Order status (e.g., FILLED, NEW)
        order_id = message['o']['i']  # Order ID
        kind_order = str(message['o']['c'])[:2] #getting kind of operation on grid (GD, TP, SL, IN, UL etc)
        
        # Filter for SYMBOL pair and when order is filled
        if symbol == grid.symbol and order_status == 'FILLED':
            
            match kind_order:
                case "IN": #the event is entry
                    print(f"ENTRY operation: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    
                
                case "GD": #the event taken is in grid
                    print(f"GRID operation: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    # get the current position
                    # calculate unload price and quantity
                    # delete existing unload order
                    # post unload
                    
                                    
                case "UL": #the event is unload
                    print(f"UNLOAD operation: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    # delete all open orders (grid, tp, sl)
                    # read and load new entry point: price and quantity
                    # generate new grid with new entry
                    # post grid
                    # post SL
                    # post TP
                    
                
                case "SL": #the event is stop loss
                    print(f"STOP_LOSS operation, {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    # close all open orders from list grid
                    close_websocket()
                
                case "TP": #the event is take profit
                    print(f"TAKE_PROFIT operation: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                    # close all open orders from grid list
                    close_websocket()
                    
                case _:
                    print(f"No kind operation")
                    close_websocket()
            





def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws):
    print("WebSocket connection closed")

def on_open(ws):
    print("WebSocket connection established")

def start_futures_stream():
    """Start WebSocket stream to monitor futures order status in real-time."""
    global ws  # Reference the global WebSocket variable
    try:
        # Create a listen key for the futures user data stream
        listen_key = client.futures_stream_get_listen_key()

        # Initialize the WebSocket connection
        ws = WebSocketApp(f"wss://fstream.binance.com/ws/{listen_key}",
                          on_message=on_message,
                          on_error=on_error,
                          on_close=on_close)

        # Run the WebSocket connection
        ws.on_open = on_open
        ws.run_forever()

        # Keep the stream alive by renewing the listen key every 30 minutes
        while True:
            time.sleep(30 * 60)
            client.futures_stream_keepalive(listen_key)

    except Exception as e:
        print(f"Error in WebSocket connection: {str(e)}")

def close_websocket():
    """Close the WebSocket connection."""
    if ws is not None:
        ws.close()
        print("WebSocket connection closed.")

if __name__ == "__main__":
    try:
        start_futures_stream()
    except KeyboardInterrupt:
        close_websocket()  # Close WebSocket on keyboard interrupt