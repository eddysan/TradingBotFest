import json
from binance.client import Client
from binance.streams import BinanceSocketManager
from websocket import WebSocketApp
import time
import logging
from package_common import *
from package_theloadunload import *
from package_cardiac import *
from package_clean import *
from package_recoveryzone import *

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
    logging.debug(f"MESSAGE RECEIVED -->: {message}")
    message = json.loads(message) #message received converted to json
    symbol = message['o']['s']  # Symbol lie XRPUSDT
    strategy = get_strategy(symbol)  # reading strategy type

    match strategy:
        case "THE_LOAD_UNLOAD_GRID": # The Load UnLoad strategy, static grid
            if message['e'] == 'ORDER_TRADE_UPDATE' and message['o']['X'] == 'FILLED': #just attend filled messaged
                grid = LUGrid(symbol)
                grid.attend_message(message)

        case "TLU_CARDIAC": # cardiac operation using re purchase and SL TP and unload lines
            if message['e'] == 'ORDER_TRADE_UPDATE' and message['o']['X'] == 'FILLED':  # just attend filled messaged
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

        case "RECOVERY_ZONE": # in case of recovery zone operation
            rz = RecoveryZone(symbol)
            rz.operate(message)



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