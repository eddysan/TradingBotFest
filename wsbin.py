import json
from binance.client import Client
from binance.streams import BinanceSocketManager
from websocket import WebSocketApp
import time
import logging
from package_common import *
from package_tlu import *
from package_cardiac import *
from package_clean import *

# logging config
os.makedirs('logs', exist_ok=True) # creates logs directory if doesn't exist

# Create a logger object
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Overall logger level

console_handler = logging.StreamHandler()  # Logs to console
console_handler.setLevel(logging.INFO)  # Only log INFO and above to console

file_handler = logging.FileHandler(f"logs/positions.log")  # Logs to file
file_handler.setLevel(logging.DEBUG)  # Log DEBUG and above to file

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s') # formatter
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

if logger.hasHandlers(): # Clear any previously added handlers (if needed)
    logger.handlers.clear()

logger.addHandler(console_handler)
logger.addHandler(file_handler)


ws = None  # Global variable for WebSocket connection

client = get_connection()

def on_message(ws, message):
    message = json.loads(message) #message received
    symbol = message['o']['s']  # Symbol lie XRPUSDT
    position_side = message['o']['ps']  # position side like LONG or SHORT
    logging.debug(f"{symbol}_{position_side} MESSAGE RECEIVED: {message}")

    if message.get('e') == 'ORDER_TRADE_UPDATE' and message['o']['X'] == 'FILLED':
        strategy = get_strategy(f"{symbol}_{position_side}") # reading strategy type

        match strategy:
            case "TLU_GRID": # Load and UnLoad strategy, static grid
                transaction_type = get_transaction_type(message)
                client_order_id = str(message['o']['c']).split('_')  # client order id
                coi_entry_number = int(client_order_id[3]) # number of entry like 1, 2, 3 in grid

                grid = LUGrid(f"{symbol}_{position_side}")
                
                match transaction_type:
                    case "IN": #the event is entry
                        logging.info(f"{symbol}_{position_side} IN order: price: {message['o']['p']}, quantity: {message['o']['q']}")
                        grid.update_current_position() # read position information at first the position will be same as entry_line
                        grid.post_tp_order() # when an entry line is taken, then take profit will be posted
                        grid.write_data_grid()
                    
                    case "GD": #the event taken is in grid
                        logging.info(f"{symbol}_{position_side} GD order: price: {message['o']['p']}, quantity: {message['o']['q']}")
                        grid.update_current_position() #read current position
                        clean_order(symbol, position_side, 'UL') # clean unload order if there is an unload order opened
                        grid.post_ul_order()
                    
                        # if the until last line is taken, then the SL will be replaced by hedge order
                        if (coi_entry_number == (len(grid.data_grid['grid_body']) - 1)) and grid.data_grid['hedge'] == True:
                            clean_order(symbol, position_side,'SL') # clean stop loss order
                            grid.post_hedge_order()
                        
                        grid.write_data_grid() # saving all configuration to json

                    case "UL": #the event is unload
                        logging.info(f"{symbol}_{position_side} UL order: price: {message['o']['p']}, quantity: {message['o']['q']}")
                        grid.update_current_position() #read current position
                        grid.update_entry_line() # updating entry line from current_line values
                        clean_open_orders(symbol, position_side) # clean all order for the position side
                        clean_order(symbol,position_side, 'HD') # clean hedge order if there is a hedge order
                        grid.generate_grid() # generate new grid points
                        grid.post_sl_order() # post stop loss order
                        grid.post_grid_order() # generate new grid and post it, taking entry price as entry and post it
                        grid.post_tp_order() # post take profit order
                        grid.write_data_grid() # saving all configuration to json
                    
                    case "SL": #the event is stop loss
                        logging.info(f"{symbol}_{position_side} SL order: price: {message['o']['p']}, quantity: {message['o']['q']}")
                        # close all open orders from list grid
                    
                    case "TP": #the event is take profit
                        logging.info(f"{symbol}_{position_side} TP order: price: {message['o']['p']}, quantity: {message['o']['q']}")
                        # close all open orders from grid list
                    
                    case "HD": #the event is hedge
                        logging.info(f"{symbol}_{position_side} TP order: price: {message['o']['p']}, quantity: {message['o']['q']}")
                        clean_open_orders(symbol, position_side) # clean all orders
                        grid.write_data_grid() # saving all configuration to json

                    case _:
                        logging.warning(f"{symbol}_{position_side} No matching operation for {symbol}")
                        print(f"No kind operation")
            
            case "TLU_CARDIAC": # cardiac operation using re purchase and SL TP and unload lines
                grid = CardiacGrid(f"{symbol}_{position_side}")
                clean_open_orders(symbol, position_side) # clean all open orders
                grid.update_current_position() # update current position to current_line
                
                if grid.data_grid['current_line']['active']:
                    grid.generate_stop_loss()
                    grid.post_stop_loss_order()
                
                    if grid.data_grid['take_profit_line']['enabled']:
                        grid.generate_take_profit()
                        grid.post_take_profit_order()
                
                    if grid.data_grid['unload_line']['enabled']:
                        grid.generate_unload()
                        grid.post_unload_order()
            
                grid.write_data_grid()


def on_error(ws, error):
    logging.error(f"Error occurred: {error}")
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    logging.info(f"WebSocket closed with status: {close_status_code}, message: {close_msg}")
    print(f"WebSocket connection closed: {close_status_code} - {close_msg}")

def on_open(ws):
    logging.info("WebSocket connection established")
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
        ws.run_forever(ping_interval=120, ping_timeout=20) # Ping every 120 seconds, wait up to 20 seconds for Pong

        # Keep the stream alive by renewing the listen key every 30 minutes
        while True:
            time.sleep(30 * 60)
            client.futures_stream_keepalive(listen_key)

    except Exception as e:
        print(f"Error in WebSocket connection: {str(e)}")
        time.sleep(5)  # Wait before attempting to reconnect

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