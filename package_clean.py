#!/usr/bin/env python3
from binance.client import Client
import logging
from package_common import *

# clean all open orders
def clean_open_orders(symbol, position_side):
        
    logging.debug(f"{symbol}_{position_side} CLEAN ALL OPEN ORDERS...")
    client = get_connection()

    # getting all open orders
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)
        
    except Exception as e:
        logging.exception(f"{symbol}_{position_side} There is an exception retrieving orders {e}")
        return

    if not open_orders:
        logging.info(f"{symbol}_{position_side} There is no orders to cancel.")
        return

    for order in open_orders:
        try:
            if order['positionSide'] == position_side:
                response = client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                logging.info(f"{symbol}_{position_side} {response['type']} | Price: {response['price']} | Quantity: {response['origQty']}...CANCELLED")

        except Exception as e:
            logging.exception(f"{symbol}_{position_side} Error cancelling orders: {e} ")

    logging.info(f"{symbol}_{position_side} All open orders cancelled and cleared.")


# clean entire grid
def clean_order(symbol, position_side, kind_operation):

    global filtered_orders
    logging.debug(f"{symbol}_{position_side} CLEANING {kind_operation} ORDERS...")

    client = get_connection()

    # getting all open orders
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)

    except Exception as e:
        logging.exception(f"{symbol}_{position_side} There is an exception retrieving orders {e}")
        return

    if not open_orders:
        logging.info(f"{symbol}_{position_side} There is no orders to cancel.")
        return

    match kind_operation:
        case "GD": # filter grid
            side = 'BUY' if position_side == 'LONG' else 'SELL'
            filtered_orders = [
                order for order in open_orders
                if order['positionSide'] == position_side and order['type'] == 'LIMIT' and order['side'] == side
            ]

        case "UL": # filtering unload
            side = 'SELL' if position_side == 'LONG' else 'BUY'
            filtered_orders = [
                order for order in open_orders
                if order['positionSide'] == position_side and order['type'] == 'LIMIT' and order['side'] == side
            ]

        case "TP": # filtering take profit
            side = 'SELL' if position_side == 'LONG' else 'BUY'
            filtered_orders = [
                order for order in open_orders
                if order['positionSide'] == position_side and order['type'] == 'TAKE_PROFIT_MARKET' and order['side'] == side
            ]

        case "SL": # filtering stop loss
            side = 'SELL' if position_side == 'LONG' else 'BUY'
            filtered_orders = [
                order for order in open_orders
                if order['positionSide'] == position_side and order['type'] == 'STOP_MARKET' and order['side'] == side
            ]

        case "HD":  # filtering hedge position for operation
            side = 'SELL' if position_side == 'LONG' else 'BUY'
            hedge_position = 'SHORT' if position_side == 'LONG' else 'LONG'
            filtered_orders = [
                order for order in open_orders
                if order['positionSide'] == hedge_position and order['type'] == 'STOP_MARKET' and order['side'] == side
            ]

        case _:
            logging.info(f"{kind_operation} missmatch")

    if not filtered_orders:
        logging.info(f"{symbol}_{position_side} There is no orders to cancel.")
        return

    # cleaning orders
    for order in filtered_orders:
        try:
            response = client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])  # Cancelling order
        except Exception as e:
            logging.exception(f"{symbol}_{position_side} Error cancelling order: {e} ")

        # Clear grid_body after all cancellations
        logging.info(f"{symbol}_{position_side} All {kind_operation} orders cancelled and cleared.")



