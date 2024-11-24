#!/usr/bin/env python3
from binance.client import Client
import logging
from connection_pack import *

# clean all open orders
def clean_open_orders(symbol, position_side):
        
    logging.info(f"{symbol}_{position_side} CLEAN ALL OPEN ORDERS...")
        
    # getting all open orders
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)
        
    except Exception:
        logging.exception("{self.operation_code} There is no open orders to clear")
            
    for order in open_orders:
        try:
            # Cancel multiple orders at once
            response = self.client.futures_cancel_order(symbol=op_symbol, orderId=order['orderId'])
            logging.debug(f"{self.operation_code} Order to cancel: {order}")
            logging.debug(f"{self.operation_code} Binance response to cancel: {response}")
            logging.info(f"{self.operation_code} {response['type']} | Price: {response['price']} | Quantity: {response['origQty']}")

        except Exception as e:
            logging.exception(f"{self.operation_code} Error cancelling orders: {e} ")

    logging.info(f"{self.operation_code} All open orders cancelled and cleared.")