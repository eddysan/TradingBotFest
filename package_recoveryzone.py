from binance.client import Client
import json
import logging
import os
from package_common import *

def input_data():
    logging.debug(f"INPUT DATA")
    config = read_config_data("config/recoveryzone.config") #reading default config file

    # INPUT symbol
    config['symbol'] = input(f"Symbol (BTC): ").upper() + 'USDT'  # getting symbol

    # INPUT side
    config['input_side'] = input(f"Side (LONG|SHORT): ").upper() or 'LONG'  # getting position side for input
    ps = config['input_side']
    ops = 'SHORT' if ps == 'LONG' else 'LONG'

    # Getting precisions for the symbol
    info = client.futures_exchange_info()['symbols']
    symbol_info = next((x for x in info if x['symbol'] == config['symbol']), None)

    # INPUT entries
    entries = int(input(f"Number of entries (1|2): ") or 1)

    # Retrieve precision filter
    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            config['step_size'] = float(f['stepSize'])
        elif f['filterType'] == 'PRICE_FILTER':
            config['tick_size'] = float(f['tickSize'])

    config['price_precision'] = symbol_info['pricePrecision']
    config['quantity_precision'] = symbol_info['quantityPrecision']

    response = client.futures_position_information(symbol=config['symbol'])  # fetch current position information
    for position_info in response:
        if float(position_info['positionAmt']) != 0: # check if there is an operation on position side
            cps = position_info['positionSide']
            print(
                f"There is a current position as entry values... \n"
                f"Position side: {position_info['positionSide']} \n"
                f"Entry Price: {position_info['entryPrice']} \n"
                f"Entry Quantity: {abs(float(position_info['positionAmt']))}")
            
            config[cps]['entry_line']['price'] = round_to_tick(float(position_info['entryPrice']), config['tick_size'])
            config[cps]['entry_line']['quantity'] = abs(float(position_info['positionAmt']))
            config[cps]['entry_line']['status'] = 'FILLED'


    config['risk']['product_factor'] = round((config['risk']['target_factor'] + 1) / config['risk']['target_factor'],2)  # generating product factor
    # getting wallet current balance
    config['risk']['wallet_balance_usdt'] = round(next((float(b['balance']) for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0), 2)

    # INPUT price and quantity for long and short
    if config[ps]['entry_line']['status'] == 'FILLED': #if entry line is filed then just post hedge points
        config[ops]['entry_line']['price'] = round_to_tick(float(input(f"Hedge price ($): ")), config['tick_size']) # entry price fot its hedge position
        config[ops]['entry_line']['quantity'] = round(config['risk']['product_factor'] * config[ps]['entry_line']['quantity'], config['quantity_precision'])

    if config[ps]['entry_line']['status'] != 'FILLED': # there is no current position, we should filled from scratch
        config[ps]['entry_line']['price'] = round_to_tick(float(input(f"Entry price ($): ")), config['tick_size'])  # entry price for long position
        config[ops]['entry_line']['price'] = round_to_tick(float(input(f"Hedge price ($): ")), config['tick_size'])  # entry price for long position
        config[ops]['entry_line']['type'] = 'STOP_MARKET'
        config[ps]['entry_line']['distance'] = get_distance(config[ps]['entry_line']['price'],config[ops]['entry_line']['price'])  # getting distance between prices
        suggested_quantity = round((config['risk']['wallet_balance_usdt'] * config['risk']['min_risk']) / config[ps]['entry_line']['distance'], 2)  # getting the 1% or more of wallet
        # INPUT quantity
        usdt_quantity = float(input(f"Entry quantity ({suggested_quantity}$): ") or suggested_quantity)
        config[ps]['entry_line']['quantity'] = round(usdt_quantity / config[ps]['entry_line']['price'],config['quantity_precision']) #quantity converted to coins
        config[ops]['entry_line']['quantity'] = round(config['risk']['product_factor'] * config[ps]['entry_line']['quantity'], config['quantity_precision']) #short quantity applied by product factor
        config[ps]['entry_line']['status'] = 'NEW'

    if config[ps]['take_profit_line']['enabled']:
        config[ps]['take_profit_line']['price'] = round_to_tick(float(input(f"Take profit price: ")),config['tick_size'])

    write_config_data('ops', f"{config['symbol']}.json", config)

    return config['symbol']


class RecoveryZone:
    def __init__(self, symbol):
        # getting operation code
        self.symbol = symbol
        self.data_grid = read_config_data(f"ops/{self.symbol}.json")  # reading config file

    # post both orders, limit and hedge
    def post_orders(self):
        self.pos_side = self.data_grid['input_side']
        self.opos_side = 'SHORT' if self.pos_side == 'LONG' else 'LONG'

        if self.data_grid[self.pos_side]['entry_line']['status'] == 'FILLED': #there is a current position
            post_hedge_order(self.symbol, self.data_grid[self.opos_side]['entry_line'])
            post_take_profit_order(self.symbol, self.data_grid[self.pos_side]['take_profit_line'])

        if self.data_grid[self.pos_side]['entry_line']['status'] != 'FILLED': #there is no position and all is new
            post_limit_order(self.symbol, self.data_grid[self.pos_side]['entry_line'])
            post_hedge_order(self.symbol, self.data_grid[self.opos_side]['entry_line'])
            post_take_profit_order(self.symbol, self.data_grid[self.pos_side]['take_profit_line'])

        write_config_data('ops',f"{self.symbol}.json",self.data_grid)

    # operate
    def attend_message(self, message):
        if message['o']['X'] != 'FILLED': # Skip processing unless the message status is 'FILLED'
            return

        self.symbol = message['o']['s']  # symbol
        self.pos_side = message['o']['ps'] #getting position side
        self.opos_side = 'SHORT' if self.pos_side == 'LONG' else 'LONG'

        if message['o']['ot'] == 'LIMIT':  # the operation is LIMIT generally first entry
            logging.info(f"{self.symbol}_{self.pos_side} - RECOVERY_ZONE - ENTRY_LINE - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")
            write_config_data('ops', f"{self.symbol}.json", self.data_grid)

        if message['o']['ot'] == 'STOP_MARKET' and message['o']['cp'] == False:  # hedge order taken and close position is false
            logging.info(
                f"{self.symbol}_{self.pos_side} - RECOVERY_ZONE - HEDGE - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")
            clean_all_open_orders(self.symbol)
            self.update_current_position()  # updating position before operate
            if float(self.data_grid['LONG']['entry_line']['quantity']) != float(self.data_grid['SHORT']['entry_line']['quantity']): #if the amounts are equal
                self.data_grid['risk']['min_risk'] = round(self.data_grid['risk']['min_risk'] * self.data_grid['risk']['product_factor'],2)  # increasing risk

                if self.data_grid['risk']['min_risk'] < self.data_grid['risk']['max_risk']:  # if risk is more than max then both operations should be same
                    new_quantity = float((self.data_grid['risk']['product_factor'] * self.data_grid[self.pos_side]['entry_line']['quantity']) - self.data_grid[self.opos_side]['entry_line']['quantity'])
                    self.data_grid[self.opos_side]['entry_line']['quantity'] = round(new_quantity,self.data_grid['quantity_precision'])
                    post_hedge_order(self.symbol, self.data_grid[self.opos_side]['entry_line'])

                else:
                    new_quantity = self.data_grid[self.pos_side]['entry_line']['quantity'] - self.data_grid[self.opos_side]['entry_line']['quantity']
                    self.data_grid[self.opos_side]['entry_line']['quantity'] = round(new_quantity, self.data_grid['quantity_precision'])  # same amount
                    post_hedge_order(self.symbol, self.data_grid[self.opos_side]['entry_line'])

                self.generate_points()
                post_take_profit_order(self.symbol, self.data_grid['LONG']['take_profit_line'])
                post_stop_loss_order(self.symbol, self.data_grid['LONG']['stop_loss_line'])
                post_take_profit_order(self.symbol, self.data_grid['SHORT']['take_profit_line'])
                post_stop_loss_order(self.symbol, self.data_grid['SHORT']['stop_loss_line'])

            write_config_data('ops',f"{self.symbol}.json",self.data_grid)

        if message['o']['ot'] == 'TAKE_PROFIT_MARKET' and message['o']['cp'] == True:  # take profit and close position
            logging.info(f"{self.symbol}_{self.pos_side} - RECOVERY_ZONE - TAKE_PROFIT - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")
            clean_order(self.symbol, self.pos_side,'GRID')
            clean_order(self.symbol, self.pos_side, 'HEDGE')

        if message['o']['ot'] == 'STOP_MARKET' and message['o']['cp'] == True:  # stop loss and close position
            logging.info(f"{self.symbol}_{self.pos_side} - RECOVERY_ZONE - STOP_LOSS - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")


    def update_current_position(self):
        logging.debug(f"{self.symbol} UPDATING CURRENT POSITION...")
        try:
            response = client.futures_position_information(symbol=self.symbol)  # fetch current position information
            for position_info in response: # Loop through the list to find the relevant position
                if position_info['positionSide'] == 'LONG':
                    self.data_grid['LONG']['entry_line']['position_side'] = position_info['positionSide']
                    self.data_grid['LONG']['entry_line']['price'] = round_to_tick(float(position_info['entryPrice']), self.data_grid['tick_size'])
                    self.data_grid['LONG']['entry_line']['quantity'] = abs(float(position_info['positionAmt']))

                if position_info['positionSide'] == 'SHORT':
                    self.data_grid['SHORT']['entry_line']['position_side'] = position_info['positionSide']
                    self.data_grid['SHORT']['entry_line']['price'] = round_to_tick(float(position_info['entryPrice']), self.data_grid['tick_size'])
                    self.data_grid['SHORT']['entry_line']['quantity'] = abs(float(position_info['positionAmt']))

            logging.debug(f"{self.symbol} Positions updated: {self.data_grid['LONG']['entry_line']} - {self.data_grid['SHORT']['entry_line']}")

        except Exception as e:
            logging.debug(f"{self.symbol} Can't update current position: {e}")


    def generate_points(self):
        logging.debug(f"{self.symbol} GENERATING POINTS...")
        # getting distances
        self.data_grid['LONG']['entry_line']['distance'] = get_distance(self.data_grid['LONG']['entry_line']['price'], self.data_grid['SHORT']['entry_line']['price'])
        self.data_grid['SHORT']['entry_line']['distance'] = get_distance(self.data_grid['SHORT']['entry_line']['price'], self.data_grid['LONG']['entry_line']['price'])

        self.data_grid['LONG']['break_even_line']['win_distance'] = round(self.data_grid['LONG']['entry_line']['distance'] * self.data_grid['risk']['target_factor'] ,2)
        self.data_grid['LONG']['break_even_line']['lost_distance'] = round(self.data_grid['SHORT']['entry_line']['distance'] * (self.data_grid['risk']['target_factor']+1), 2)

        self.data_grid['SHORT']['break_even_line']['win_distance'] = round(self.data_grid['SHORT']['entry_line']['distance'] * self.data_grid['risk']['target_factor'], 2)
        self.data_grid['SHORT']['break_even_line']['lost_distance'] = round(self.data_grid['LONG']['entry_line']['distance'] * self.data_grid['risk']['target_factor']+1, 2)

        # BREAK EVEN points
        self.data_grid['LONG']['break_even_line']['price'] = round_to_tick(
            abs(self.data_grid['LONG']['entry_line']['price'] * (1 + (self.data_grid['LONG']['break_even_line']['win_distance']/100))),
            self.data_grid['tick_size']) #break even price for LONG side
        self.data_grid['LONG']['break_even_line']['win_quantity'] = self.data_grid['LONG']['entry_line']['quantity']
        self.data_grid['LONG']['break_even_line']['lost_quantity'] = self.data_grid['SHORT']['entry_line']['quantity']
        self.data_grid['LONG']['break_even_line']['win_cost'] = round(
            self.data_grid['LONG']['break_even_line']['win_quantity'] * self.data_grid['LONG']['break_even_line']['price'], 2) #cost for LONG side as win
        self.data_grid['LONG']['break_even_line']['lost_cost'] = round(
            self.data_grid['LONG']['break_even_line']['lost_quantity'] * self.data_grid['LONG']['break_even_line']['price'], 2)

        self.data_grid['SHORT']['break_even_line']['price'] = round_to_tick(
            abs(self.data_grid['SHORT']['entry_line']['price'] * (1 - (self.data_grid['SHORT']['break_even_line']['win_distance']/100))),
            self.data_grid['tick_size']) # break even price for short side
        self.data_grid['SHORT']['break_even_line']['win_quantity'] = self.data_grid['SHORT']['entry_line']['quantity']
        self.data_grid['SHORT']['break_even_line']['lost_quantity'] = self.data_grid['LONG']['entry_line']['quantity']
        self.data_grid['SHORT']['break_even_line']['win_cost'] = round(
            self.data_grid['SHORT']['break_even_line']['win_quantity'] * self.data_grid['SHORT']['break_even_line']['price'], 2)
        self.data_grid['SHORT']['break_even_line']['lost_cost'] = round(
            self.data_grid['SHORT']['break_even_line']['lost_quantity'] * self.data_grid['SHORT']['break_even_line']['price'] ,2)

        # TAKE PROFIT points
        self.data_grid['LONG']['take_profit_line']['price'] = round_to_tick(
            abs(self.data_grid['LONG']['break_even_line']['price'] * (1 + (self.data_grid['LONG']['take_profit_line']['distance'] / 100))),
            self.data_grid['tick_size'])

        self.data_grid['SHORT']['take_profit_line']['price'] = round_to_tick(
            abs(self.data_grid['SHORT']['break_even_line']['price'] * (1 - (self.data_grid['SHORT']['take_profit_line']['distance'] / 100))),
            self.data_grid['tick_size'])

        # STOP LOSS POINTS
        self.data_grid['LONG']['stop_loss_line']['price'] = self.data_grid['SHORT']['take_profit_line']['price']
        self.data_grid['SHORT']['stop_loss_line']['price'] = self.data_grid['LONG']['take_profit_line']['price']





