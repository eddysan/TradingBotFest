
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

    xinfo = get_exchange_info(config['symbol'])
    config['tick_size'] = xinfo['tick_size']
    config['price_precision'] = xinfo['price_precision']
    config['quantity_precision'] = xinfo['quantity_precision']

    # INPUT number of entries for order
    nentries = int(input(f"Number of entries (1|2): ") or 1)

    response = client.futures_position_information(symbol=config['symbol'])  # fetch current position information
    for position_info in response:
        if float(position_info['positionAmt']) != 0 and position_info['positionSide'] == ps: # check if there is an operation on position side
            print(
                f" There is a current position as entry values... \n"
                f" Position side: {position_info['positionSide']} \n"
                f" Entry Price: {position_info['entryPrice']} \n"
                f" Entry Quantity: {abs(float(position_info['positionAmt']))}")

            sec_price = float(input(f"Entry second price ($): "))
            config[ps]['entry_line'] = [{
                'label':'first entry',
                'price': round_to_tick(float(position_info['entryPrice']), config['tick_size']),
                'quantity': abs(float(position_info['positionAmt'])),
                'side': 'BUY' if ps == 'LONG' else 'SELL',
                'position_side': ps,
                'cost': round( float(position_info['entryPrice']) * abs(float(position_info['positionAmt'])), 2),
                'status':'FILLED'},
                {'label': 'second entry',
                'price': round_to_tick(sec_price, config['tick_size']),
                'quantity': abs(float(position_info['positionAmt'])) if nentries == 2 else 0,
                 'side': 'BUY' if ps == 'LONG' else 'SELL',
                 'position_side': ps,
                 'cost': round(sec_price * abs(float(position_info['positionAmt'])) , 2),
                'status': 'NEW' if nentries == 2 else 'CANCELLED'
                }]
            config[ps]['take_profit_line']['price'] = round_to_tick(float(input(f"Take profit price: ")),config['tick_size'])

    config['risk']['product_factor'] = round((config['risk']['target_factor'] + 1) / config['risk']['target_factor'],2)  # generating product factor
    config['risk']['wallet_balance_usdt'] = get_wallet_balance_usdt() # getting wallet current balance

    if not config[ps]['entry_line']: #if entry line is empty
        first_quantity = 0
        second_quantity = 0
        first_price = float(input(f"First entry price ($): "))  # entry price for long position
        second_price = float(input(f"Second entry price ($): "))  # entry price for long position
        config[ps]['take_profit_line']['price'] = round_to_tick(float(input(f"Take profit price: ")),config['tick_size'])
        distance = get_distance(first_price, second_price)  # getting distance between prices
        suggested_quantity = round((config['risk']['wallet_balance_usdt'] * config['risk']['min_risk']) / distance, 2)  # getting the 1% or more of wallet
        # INPUT quantity
        usdt_quantity = float(input(f"Entry quantity ({suggested_quantity}$): ") or suggested_quantity)
        if nentries == 1:
            first_quantity = round(usdt_quantity / first_price, config['quantity_precision']) #quantity converted to coins
            second_quantity = 0
        if nentries == 2:
            first_quantity = round((usdt_quantity/2) / first_price, config['quantity_precision'])
            second_quantity = round((usdt_quantity/2) / second_price, config['quantity_precision'])

        config[ps]['entry_line'] = [{
            'label':'first entry',
            'price': round_to_tick(first_price, config['tick_size']),
            'quantity': first_quantity,
            'side': 'BUY' if ps == 'LONG' else 'SELL',
            'position_side': ps,
            'cost': round(first_price * first_quantity, 2),
            'status':'NEW'},
            {'label':'second entry',
            'price': round_to_tick(second_price, config['tick_size']),
            'quantity': second_quantity,
             'side': 'BUY' if ps == 'LONG' else 'SELL',
             'position_side': ps,
             'cost': round(second_price * second_quantity,2),
            'status': 'NEW' if second_quantity != 0 else 'CANCELLED'
            }]

    # INPUT hedge points
    if ops == 'LONG':
        config[ops]['hedge_line']['price'] = round_to_tick(config[ps]['entry_line'][1]['price'] * (1 + (config['risk']['hedge_distance']/100) ), config['tick_size'])
    elif ops == 'SHORT':
        config[ops]['hedge_line']['price'] = round_to_tick(config[ps]['entry_line'][1]['price'] * (1 - (config['risk']['hedge_distance']/100)), config['tick_size'])

    total_quantity = config[ps]['entry_line'][0]['quantity'] + config[ps]['entry_line'][1]['quantity']
    config[ops]['hedge_line']['quantity'] = round(config['risk']['product_factor'] * total_quantity, config['quantity_precision']) #short quantity applied by product factor

    write_config_data('ops', f"{config['symbol']}.json", config)

    return config['symbol']


class RecoveryZone:
    def __init__(self, symbol):
        # getting operation code
        self.symbol = symbol
        self.data_grid = read_config_data(f"ops/{self.symbol}.json")  # reading config file
        self.pos_side = 'NONE' #initialize data
        self.opos_side = 'NONE' #initialize data

    # post both orders, limit and hedge
    def post_orders(self):
        self.pos_side = self.data_grid['input_side']
        self.opos_side = 'SHORT' if self.pos_side == 'LONG' else 'LONG'

        post_grid_order(self.symbol, self.data_grid[self.pos_side]['entry_line']) # posting limit orders
        post_hedge_order(self.symbol, self.data_grid[self.opos_side]['hedge_line'])
        if self.data_grid[self.pos_side]['take_profit_line']['enabled']:
            post_take_profit_order(self.symbol, self.data_grid[self.pos_side]['take_profit_line'])

        write_config_data('ops',f"{self.symbol}.json",self.data_grid)

    # operate
    def attend_message(self, message):
        if message['o']['X'] != 'FILLED': # Skip processing unless the message status is 'FILLED'
            return

        self.pos_side = message['o']['ps'] #getting position side
        self.opos_side = 'SHORT' if self.pos_side == 'LONG' else 'LONG'

        if message['o']['ot'] == 'LIMIT':  # the operation is LIMIT generally first and/or second entry
            logging.info(f"{self.symbol}_{self.pos_side} - RECOVERY_ZONE - hedge_line - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")
            self.update_current_position() # updating position before operate
            if self.data_grid[self.pos_side]['trailing_stop_line']['enabled']:
                clean_order(self.symbol, self.pos_side, 'TRAILING_STOP_MARKET') #clean a trailing stop if there is one
                self.generate_trailing_stop()
                post_trailing_stop_order(self.symbol, self.data_grid[self.pos_side]['trailing_stop_line'])

            write_config_data('ops', f"{self.symbol}.json", self.data_grid)
            return

        if message['o']['ot'] == 'STOP_MARKET' and message['o']['cp'] == False:  # hedge order taken and close position is false
            logging.info(f"{self.symbol}_{self.pos_side} - RECOVERY_ZONE - HEDGE - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")
            self.update_current_position()  # updating position before operate
            clean_all_open_orders(self.symbol)
            if float(self.data_grid['LONG']['hedge_line']['quantity']) != float(self.data_grid['SHORT']['hedge_line']['quantity']): #if the amounts are equal
                self.data_grid['risk']['min_risk'] = round(self.data_grid['risk']['min_risk'] * self.data_grid['risk']['product_factor'],2)  # increasing risk

                if float(self.data_grid['risk']['min_risk']) < float(self.data_grid['risk']['max_risk']):  # if risk is more than max then both operations should be same
                    new_quantity = float((self.data_grid['risk']['product_factor'] * self.data_grid[self.pos_side]['hedge_line']['quantity']) - self.data_grid[self.opos_side]['hedge_line']['quantity'])
                    self.data_grid[self.opos_side]['hedge_line']['quantity'] = round(new_quantity,self.data_grid['quantity_precision'])
                    self.generate_recovery_line()
                    post_hedge_order(self.symbol, self.data_grid[self.opos_side]['recovery_line'])

                else:
                    new_quantity = self.data_grid[self.pos_side]['hedge_line']['quantity'] - self.data_grid[self.opos_side]['hedge_line']['quantity']
                    self.data_grid[self.opos_side]['hedge_line']['quantity'] = round(new_quantity, self.data_grid['quantity_precision'])  # same amount
                    self.generate_recovery_line()
                    post_hedge_order(self.symbol, self.data_grid[self.opos_side]['recovery_line'])

                self.generate_distances()
                self.generate_break_even_points()
                self.generate_take_profit_points()
                self.generate_stop_loss_points()
                post_take_profit_order(self.symbol, self.data_grid['LONG']['take_profit_line'])
                post_stop_loss_order(self.symbol, self.data_grid['LONG']['stop_loss_line'])
                post_take_profit_order(self.symbol, self.data_grid['SHORT']['take_profit_line'])
                post_stop_loss_order(self.symbol, self.data_grid['SHORT']['stop_loss_line'])

            write_config_data('ops',f"{self.symbol}.json",self.data_grid)
            return

        if message['o']['ot'] == 'TAKE_PROFIT_MARKET' and message['o']['cp'] == True:  # take profit and close position
            logging.info(f"{self.symbol}_{self.pos_side} - RECOVERY_ZONE - TAKE_PROFIT - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")
            clean_order(self.symbol, self.pos_side,'GRID')
            clean_order(self.symbol, self.opos_side, 'HEDGE')
            return

        if message['o']['ot'] == 'STOP_MARKET' and message['o']['cp'] == True:  # stop loss and close position
            logging.info(f"{self.symbol}_{self.pos_side} - RECOVERY_ZONE - STOP_LOSS - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")
            clean_order(self.symbol, self.pos_side,'GRID')
            clean_order(self.symbol, self.opos_side, 'HEDGE')
            return

        if message['o']['ot'] == 'TRAILING_STOP_MARKET': #when trailing stop is taken (not activation price), trailing stop protection
            logging.info(f"{self.symbol}_{self.pos_side} - TRAILING_STOP_MARKET - Price: {message['o']['p']} | Quantity: {message['o']['q']} ...FILLED")
            clean_order(self.symbol, self.pos_side,'GRID') #delete a LIMIT order if there is another entry
            clean_order(self.symbol, self.opos_side, 'HEDGE') #delete hedge order
            return


    def update_current_position(self):
        logging.debug(f"{self.symbol} UPDATING CURRENT POSITION...")
        try:
            response = client.futures_position_information(symbol=self.symbol)  # fetch current position information
            for position_info in response: # Loop through the list to find the relevant position
                if position_info['positionSide'] == 'LONG':
                    self.data_grid['LONG']['hedge_line']['position_side'] = position_info['positionSide']
                    self.data_grid['LONG']['hedge_line']['price'] = round_to_tick(float(position_info['entryPrice']), self.data_grid['tick_size'])
                    self.data_grid['LONG']['hedge_line']['quantity'] = abs(float(position_info['positionAmt']))

                if position_info['positionSide'] == 'SHORT':
                    self.data_grid['SHORT']['hedge_line']['position_side'] = position_info['positionSide']
                    self.data_grid['SHORT']['hedge_line']['price'] = round_to_tick(float(position_info['entryPrice']), self.data_grid['tick_size'])
                    self.data_grid['SHORT']['hedge_line']['quantity'] = abs(float(position_info['positionAmt']))

            logging.debug(f"{self.symbol} Positions updated: {self.data_grid['LONG']['hedge_line']} - {self.data_grid['SHORT']['hedge_line']}")

        except Exception as e:
            logging.debug(f"{self.symbol} Can't update current position: {e}")


    def generate_distances(self):
        logging.debug(f"{self.symbol} GENERATING DISTANCES...")
        # getting distances
        self.data_grid['LONG']['hedge_line']['distance'] = get_distance(self.data_grid['LONG']['hedge_line']['price'], self.data_grid['SHORT']['hedge_line']['price'])
        self.data_grid['SHORT']['hedge_line']['distance'] = get_distance(self.data_grid['SHORT']['hedge_line']['price'], self.data_grid['LONG']['hedge_line']['price'])

        self.data_grid['LONG']['break_even_line']['win_distance'] = round(self.data_grid['LONG']['hedge_line']['distance'] * self.data_grid['risk']['target_factor'] ,2)
        self.data_grid['LONG']['break_even_line']['lost_distance'] = round(self.data_grid['SHORT']['hedge_line']['distance'] * (self.data_grid['risk']['target_factor']+1), 2)

        self.data_grid['SHORT']['break_even_line']['win_distance'] = round(self.data_grid['SHORT']['hedge_line']['distance'] * self.data_grid['risk']['target_factor'], 2)
        self.data_grid['SHORT']['break_even_line']['lost_distance'] = round(self.data_grid['LONG']['hedge_line']['distance'] * self.data_grid['risk']['target_factor']+1, 2)

    def generate_break_even_points(self):
        logging.debug(f"{self.symbol} GENERATING BREAK EVEN POINTS...")
        # break even points for LONG
        self.data_grid['LONG']['break_even_line']['price'] = round_to_tick(
            abs(self.data_grid['LONG']['hedge_line']['price'] * (1 + (self.data_grid['LONG']['break_even_line']['win_distance']/100))),
            self.data_grid['tick_size']) #break even price for LONG side
        self.data_grid['LONG']['break_even_line']['win_quantity'] = self.data_grid['LONG']['hedge_line']['quantity']
        self.data_grid['LONG']['break_even_line']['lost_quantity'] = self.data_grid['SHORT']['hedge_line']['quantity']
        self.data_grid['LONG']['break_even_line']['win_cost'] = round(
            self.data_grid['LONG']['break_even_line']['win_quantity'] * self.data_grid['LONG']['break_even_line']['price'], 2) #cost for LONG side as win
        self.data_grid['LONG']['break_even_line']['lost_cost'] = round(
            self.data_grid['LONG']['break_even_line']['lost_quantity'] * self.data_grid['LONG']['break_even_line']['price'], 2)
        # break even points for SHORT
        self.data_grid['SHORT']['break_even_line']['price'] = round_to_tick(
            abs(self.data_grid['SHORT']['hedge_line']['price'] * (1 - (self.data_grid['SHORT']['break_even_line']['win_distance']/100))),
            self.data_grid['tick_size']) # break even price for short side
        self.data_grid['SHORT']['break_even_line']['win_quantity'] = self.data_grid['SHORT']['hedge_line']['quantity']
        self.data_grid['SHORT']['break_even_line']['lost_quantity'] = self.data_grid['LONG']['hedge_line']['quantity']
        self.data_grid['SHORT']['break_even_line']['win_cost'] = round(
            self.data_grid['SHORT']['break_even_line']['win_quantity'] * self.data_grid['SHORT']['break_even_line']['price'], 2)
        self.data_grid['SHORT']['break_even_line']['lost_cost'] = round(
            self.data_grid['SHORT']['break_even_line']['lost_quantity'] * self.data_grid['SHORT']['break_even_line']['price'] ,2)

    def generate_take_profit_points(self):
        logging.debug(f"{self.symbol} GENERATING TAKE PROFIT POINTS...")
        # generate take profit point for LONG
        self.data_grid['LONG']['take_profit_line']['price'] = round_to_tick(
            abs(self.data_grid['LONG']['break_even_line']['price'] * (1 + (self.data_grid['LONG']['take_profit_line']['distance'] / 100))),
            self.data_grid['tick_size'])
        # generate take profit for SHORT
        self.data_grid['SHORT']['take_profit_line']['price'] = round_to_tick(
            abs(self.data_grid['SHORT']['break_even_line']['price'] * (1 - (self.data_grid['SHORT']['take_profit_line']['distance'] / 100))),
            self.data_grid['tick_size'])

    def generate_stop_loss_points(self):
        logging.debug(f"{self.symbol} GENERATING STOP LOSS POINTS...")
        self.data_grid['LONG']['stop_loss_line']['price'] = self.data_grid['SHORT']['take_profit_line']['price']
        self.data_grid['SHORT']['stop_loss_line']['price'] = self.data_grid['LONG']['take_profit_line']['price']

    def generate_recovery_line(self):
        inside_distance = get_distance(self.data_grid[self.opos_side]['hedge_line']['price'], self.data_grid[self.pos_side]['hedge_line']['price']) #getting distance between points
        target_distance = (inside_distance / 100) * self.data_grid['risk']['reduce_hedge']
        target_price = self.data_grid[self.opos_side]['hedge_line']['price'] * (1 + target_distance / 100) if self.pos_side == 'LONG' else self.data_grid[self.opos_side]['hedge_line']['price'] * (1 - target_distance / 100)
        self.data_grid[self.opos_side]['recovery_line']['price'] = round_to_tick(target_price, self.data_grid['tick_size'])
        self.data_grid[self.opos_side]['recovery_line']['quantity'] = self.data_grid[self.opos_side]['hedge_line']['quantity']

    def generate_trailing_stop(self):
        self.data_grid[self.pos_side]['trailing_stop_line']['activation_price'] = round_to_tick((self.data_grid[self.pos_side]['hedge_line']['price'] + self.data_grid[self.pos_side]['take_profit_line']['price']) / 2, self.data_grid['tick_size']) #getting the middle price for trailing
        callback_rate = get_distance(self.data_grid[self.pos_side]['trailing_stop_line']['activation_price'], self.data_grid[self.pos_side]['hedge_line']['price']) #distance between entry and take profit
        if float(callback_rate) <= 10: # the maximum distance of callback is 10
            self.data_grid[self.pos_side]['trailing_stop_line']['callback_rate'] = callback_rate
        else:
            self.data_grid[self.pos_side]['trailing_stop_line']['callback_rate'] = 10.00

        self.data_grid[self.pos_side]['trailing_stop_line']['quantity'] = self.data_grid[self.pos_side]['hedge_line']['quantity']
        self.data_grid[self.pos_side]['trailing_stop_line']['cost'] = round(self.data_grid[self.pos_side]['trailing_stop_line']['activation_price'] * self.data_grid[self.pos_side]['trailing_stop_line']['quantity'] ,2)

    def generate_stop_loss_protection(self):
        logging.debug(f"{self.symbol} GENERATING STOP LOSS PROTECTION POINT...")
        protection_distance = float(self.data_grid[self.pos_side]['stop_loss_line']['protection_distance'])
        target_price = self.data_grid[self.pos_side]['hedge_line']['price'] * (1 + protection_distance / 100) if self.pos_side == 'LONG' else self.data_grid[self.pos_side]['hedge_line']['price'] * (1 - protection_distance / 100)
        self.data_grid[self.pos_side]['stop_loss_line']['price'] = round_to_tick(target_price, self.data_grid['tick_size'])




