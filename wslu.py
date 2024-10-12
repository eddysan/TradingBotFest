import json
from binance.client import Client
from binance.streams import BinanceSocketManager
from websocket import WebSocketApp
import time
from packages import *

ws = None  # Global variable for WebSocket connection
client = get_connection()

def on_message(ws, message):

    message = json.loads(message) #message received

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
                        print(f"IN taked: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                        grid.update_current_position() # read position information at first the position will be same as entry_line
                        #grid.clean_open_orders() # clean all orders short and long orders
                        #grid.post_grid_order()
                        #grid.post_sl_order()
                        #grid.post_tp_order() # post take profit order
                        grid.write_data_grid()
                    
                case "GD": #the event taken is in grid
                        print(f"GD taked: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                        grid.update_current_position() #read current position
                        grid.clean_ul_order()
                        grid.post_ul_order()
                        #grid.post_tp_order() # post take profit order
                        grid.write_data_grid() # saving all configuration to json

                case "UL": #the event is unload
                        print(f"UL taked: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                        grid.update_current_position() #read current position
                        grid.update_entry_line() # updating entry line from current_line values
                        grid.clean_open_orders() # clean all open orders
                        grid.generate_grid() # generate new grid points
                        grid.post_grid_order() # generate new grid and post it, taking entry price as entry and post it
                        grid.post_sl_order() # post stop loss order
                        grid.post_tp_order() # post take profit order
                        grid.write_data_grid() # saving all configuration to json
                    
                case "SL": #the event is stop loss
                        print(f"SL taked: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                        # close all open orders from list grid
                    
                case "TP": #the event is take profit
                        print(f"TP taked: {grid.symbol}, price: {message['o']['p']}, quantity: {message['o']['q']}")
                        # close all open orders from grid list
                        
                case _:
                        print(f"No kind operation")
            





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