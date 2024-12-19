from concurrent.futures import ThreadPoolExecutor, as_completed

from binance.exceptions import BinanceAPIException

from package_connection import client
from functools import lru_cache
import os
import json
import math
import logging

# Reading json file, the json_file_path should include directory + file + .json extension
def read_config_data(json_file_path):
    try:
        # Use 'open' with 'os.path.exists' to minimize redundant checks
        if not os.path.exists(json_file_path):
            logging.warning(f"Config file '{json_file_path}' not found.")
            return None

        # Open and parse JSON efficiently
        with open(json_file_path, 'r') as file:
            return json.load(file)

    except (json.JSONDecodeError, FileNotFoundError) as e:
        logging.error(f"Error loading '{json_file_path}': {e}")
        return None

# Write data grid file
def write_config_data(directory, file_name, data_grid):
    # Combine path components safely and efficiently
    os.makedirs(directory, exist_ok=True)
    file_path = os.path.join(directory, file_name)

    try:
        with open(file_path, 'w', buffering=8192) as file:  # 8KB buffering for efficiency
            json.dump(data_grid, file, indent=4, separators=(',', ':'))  # Compact JSON format
    except (OSError, TypeError) as e:
        print(f"Error writing to file '{file_path}': {e}")


# get strategy from operation file
@lru_cache(maxsize=128)
def get_strategy(operation):
    try:
        return read_config_data(f"ops/{operation}.json")['strategy']
    except (TypeError, KeyError, FileNotFoundError):
        return None

# round price to tick size
def round_to_tick(price, tick_size):
    tick_increment = int(abs(math.log10(tick_size)))
    return round(price, tick_increment)

# getting distance between two points as percentage
def get_distance(first_point, second_point):
    side = 'LONG' if first_point < second_point else 'SHORT'
    if side == 'LONG':
        distance = round( ((float(second_point) - float(first_point)) / float(first_point)) * 100, 2)
        return distance
    if side == 'SHORT':
        distance = round( ((float(first_point) - float(second_point)) / float(first_point)) * 100, 2)
        return distance

def clean_all_open_orders(symbol):
    logging.debug(f"{symbol} - CLEAN ALL OPEN ORDERS...")
    try:
        # Cancel all open orders directly without fetching them first
        response = client.futures_cancel_all_open_orders(symbol=symbol)
        logging.info(f"{symbol} - All open orders cancelled")

    except Exception as e:
        # Specific handling for cases where no orders exist or other errors
        if "no orders to cancel" in str(e).lower():  # Adjust based on the Binance API response for this case
            logging.info(f"{symbol} - No open orders to cancel.")
        else:
            logging.exception(f"{symbol} - Error cancelling orders: {e}")


# clean all open orders
def clean_open_orders(symbol, position_side):
    logging.debug(f"{symbol}_{position_side} - CLEAN ALL OPEN ORDERS...")

    open_orders = client.futures_get_open_orders(symbol=symbol) # getting all open orders
    if not open_orders:
        logging.info(f"{symbol}_{position_side} - There are no orders to cancel.")
        return

    open_orders = [order for order in open_orders if order['positionSide'] == position_side] #filtering orders by position side
    if not open_orders:
        logging.info(f"{symbol}_{position_side} - There are no orders to cancel.")
        return

    def cancel_order(order):
        try:
            response = client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
            logging.info(f"{symbol}_{position_side} - {response['type']} | Price: {response['price']} | Quantity: {response['origQty']} ...CANCELLED")
        except Exception as e:
            logging.exception(f"{symbol}_{position_side} - Error cancelling order {order['orderId']}: {e}")

    # Use ThreadPoolExecutor to cancel orders concurrently
    with ThreadPoolExecutor() as executor:
        executor.map(cancel_order, open_orders)

# clean entire grid
def clean_order(symbol, position_side, kind_operation):
    logging.debug(f"{symbol}_{position_side} CLEANING {kind_operation} ORDERS...")
    open_orders = []

    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)
        open_orders = filter_operation(open_orders, position_side, kind_operation) #filtering operations by kind operation

    except Exception as e:
        logging.exception(f"{symbol}_{position_side} There is an exception retrieving orders {e}")

    if not open_orders:
        logging.info(f"{symbol}_{position_side} There is no orders to cancel.")
        return

    # cleaning orders
    def cancel_order(order):
        try:
            response = client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
            logging.info(f"{symbol}_{position_side} - {kind_operation} | Price: {response['price']} | Quantity: {response['origQty']} ...CANCELLED")

        except Exception as e:
            logging.exception(f"{symbol}_{position_side} - Error cancelling order {order['orderId']}: {e}")

    # Use ThreadPoolExecutor to cancel orders concurrently
    with ThreadPoolExecutor() as executor:
        executor.map(cancel_order, open_orders)

# filter operation
def filter_operation(open_orders, position_side, kind_operation):
    # Map operation to types and side logic
    operation_map = {
        "GRID": {
            "type": "LIMIT",
            "side": lambda ps: "BUY" if ps == "LONG" else "SELL"},
        "UNLOAD": {
            "type": "LIMIT",
            "side": lambda ps: "SELL" if ps == "LONG" else "BUY"},
        "TAKE_PROFIT": {
            "type": "TAKE_PROFIT_MARKET",
            "side": lambda ps: "SELL" if ps == "LONG" else "BUY"},
        "STOP_LOSS": {
            "type": "STOP_MARKET",
            "side": lambda ps: "SELL" if ps == "LONG" else "BUY"},
        "HEDGE": {
            "type": "STOP_MARKET",
            "side": lambda ps: ("SELL" if ps == "LONG" else "BUY"),
            "hedge_position": lambda ps: "SHORT" if ps == "LONG" else "LONG",
        },
    }

    operation = operation_map[kind_operation]
    order_type = operation["type"]
    side = operation["side"](position_side)

    # Special case for HD (hedge)
    if kind_operation == "HD":
        hedge_position = operation["hedge_position"](position_side)
        return [
            order for order in open_orders
            if order["positionSide"] == hedge_position and order["type"] == order_type and order["side"] == side
        ]

    # General case for all other operations
    return [
        order for order in open_orders
        if order["positionSide"] == position_side and order["type"] == order_type and order["side"] == side
    ]


# Post a limit order to Binance
def post_limit_order(symbol, data_line):
    try:
        # Extract fields for cleaner code and avoid redundant dictionary lookups
        side = data_line.get('side')
        position_side = data_line.get('position_side')
        price = data_line.get('price')
        quantity = data_line.get('quantity')
        label = data_line.get('label', 'LIMIT')  # Default label to 'LIMIT' if not provided

        # Skip orders with zero quantity
        if not quantity:  # Avoid unnecessary string formatting and reduce log clutter
            logging.info(f"{symbol}_{position_side} - {label} operation skipped due to zero quantity.")
            return

        # Place the order
        response = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='LIMIT',
            timeInForce='GTC',
            positionSide=position_side,
            price=price,
            quantity=quantity
        )

        logging.debug(f"{symbol}_{position_side} LIMIT order response: {response}")
        logging.info(f"{symbol}_{position_side} - {label} | Price: {price} | Quantity: {quantity} ...POSTED")

    except KeyError as ke:
        logging.error(f"{symbol}_{position_side} - Missing key in data_line for LIMIT order posting: {ke} - Data: {data_line}")
    except BinanceAPIException as e:
        if e.code == -2021:
            logging.error(f"{symbol}_{position_side} - {label} | Price: {price} ...TRIGGERED")
        else:
            logging.exception(f"{symbol}_{position_side} - Binance API Error: {e}")

# post take profit order
def post_take_profit_order(symbol, data_line):
    try:
        # Pre-fetch values for efficiency
        position_side = data_line.get('position_side')
        price = data_line.get('price')
        side = data_line.get('side')
        label = data_line.get('label')
        quantity = data_line.get('quantity')
        response = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='TAKE_PROFIT_MARKET',
            timeInForce='GTC',
            positionSide=position_side,
            stopPrice=price,
            closePosition=True
        )
        logging.debug(f"{symbol}_{position_side} Binance response: {response}")
        logging.info(f"{symbol}_{position_side} - {label} | Price: {price} | Quantity: {quantity} ...POSTED")
    except KeyError as ke:
        logging.error(f"Missing key in data_line: {ke} - Data: {data_line}")
    except BinanceAPIException as e:
        if e.code == -2021:
            logging.error(f"{symbol}_{position_side} - {label} | Price: {price} ...TRIGGERED")
        else:
            logging.exception(f"{symbol}_{position_side} - Binance API Error: {e}")


# post stop loss order
def post_stop_loss_order(symbol, data_line):
    try:
        position_side = data_line.get('position_side')
        price = data_line.get('price')
        side = data_line.get('side')
        label = data_line.get('label')
        distance = round(data_line.get('distance', 0), 2)  # Default to 0 if missing
        quantity = data_line.get('quantity')
        cost = data_line.get('cost')

        # Post the stop loss order
        response = client.futures_create_order(
            symbol=symbol,
            side=side,
            positionSide=position_side,
            type='STOP_MARKET',
            stopPrice=price,
            closePosition=True
        )

        # Unified and simplified logging
        logging.debug(f"{symbol}_{position_side} STOP_LOSS response: {response}")
        logging.info(f"{symbol}_{position_side} - {label} ({distance}%) | Price: {price} | Quantity: {quantity} | Cost: {cost} ...POSTED")

    except KeyError as ke:
        logging.error(f"Missing key in data_line: {ke} - Data: {data_line}")
    except BinanceAPIException as e:
        if e.code == -2021:
            logging.error(f"{symbol}_{position_side} - {label} | Price: {price} ...TRIGGERED")
        else:
            logging.exception(f"{symbol}_{position_side} - Binance API Error: {e}")

# post hedge order
def post_hedge_order(symbol, data_line):
    try:
        position_side = data_line.get('position_side')
        price = data_line.get('price')
        side = data_line.get('side')
        quantity = data_line.get('quantity')
        label = data_line.get('label')

        # Post the hedge order
        response = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='STOP_MARKET',
            timeInForce='GTC',
            positionSide=position_side,
            stopPrice=price,
            quantity=quantity,
            closePosition=False
        )

        logging.debug(f"{symbol}_{position_side} Post hedge order response: {response}")
        logging.info(f"{symbol}_{position_side} - {label} | Price: {price} | Quantity: {quantity} ...POSTED")

    except KeyError as ke:
        logging.error(f"Missing key in data_line: {ke} - Data: {data_line}")
    except BinanceAPIException as e:
        if e.code == -2021:
            logging.error(f"{symbol}_{position_side} - {label} | Price: {price} ...TRIGGERED")
        else:
            logging.exception(f"{symbol}_{position_side} - Binance API Error: {e}")


# post limit orders as grid
def post_grid_order(symbol, data_line):
    logging.debug(f"{symbol} POSTING BODY LINE...")

    def post_order(order):  # Helper function to post a single order
        try:
            response = client.futures_create_order(
                symbol=symbol,
                side=order['side'],
                type=order['type'],
                timeInForce='GTC',
                positionSide=order['position_side'],
                price=order['price'],
                quantity=order['quantity']
            )
            logging.debug(f"{symbol} Binance response: {response}")
            logging.info(f"{symbol} - {order['label']} | Price: {order['price']} | Quantity: {order['quantity']} | Cost: {order['cost']} ...POSTED")
            return response  # Optional: Return response if needed

        except KeyError as ke:
            logging.exception(f"{symbol} Posting grid orders: Missing key in order data: {ke}")
        except BinanceAPIException as e:
            if e.code == -2021:
                logging.error(f"{symbol}_{order['position_side']} - {order['label']} | Price: {order['price']} | Quantity: {order['quantity']} ...TRIGGERED")
            else:
                logging.exception(f"{symbol}_{order['position_side']} - Binance API Error: {e}")

    try:
        with ThreadPoolExecutor(max_workers=10) as executor:  # Adjust max_workers for concurrency
            # Submit tasks for all orders in the data_line list
            futures = [executor.submit(post_order, order) for order in data_line]

            # Process completed futures (optional: for response management)
            for future in as_completed(futures):
                try:
                    future.result()  # Ensures any exception in the thread is raised
                except Exception as e:
                    logging.exception(f"{symbol} Error in posting an order: {e}")


    except Exception as e:
        logging.exception(f"{symbol} Error in grid posting process: {e}")

