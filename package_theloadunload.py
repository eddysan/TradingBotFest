from package_common import *
from package_connection import client

# input data from console
def input_data():
    logging.info(f"LCD - THE LOAD UNLOAD...")
    config = read_config_data(f"config/theloadunload.config")

    # INPUT symbol
    symbol = input("Symbol (BTC): ").upper() + "USDT"
    config['symbol'] = symbol

    # INPUT position side (default to LONG)
    input_side = input("Side (LONG|SHORT): ").upper() or 'LONG'
    config['input_side'] = input_side

    # Getting precisions for the symbol
    info = client.futures_exchange_info()['symbols']
    symbol_info = next((x for x in info if x['symbol'] == symbol), None)

    # Retrieve precision filter
    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            config['step_size'] = float(f['stepSize'])
        elif f['filterType'] == 'PRICE_FILTER':
            config['tick_size'] = float(f['tickSize'])

    config['price_precision'] = symbol_info['pricePrecision']
    config['quantity_precision'] = symbol_info['quantityPrecision']

    # Fetch info if there is a current position
    response = client.futures_position_information(symbol=symbol)
    for position_info in response:
        if float(position_info['positionAmt']) != 0 and position_info['positionSide'] == input_side:  # if position amount is not zero, then there is a current position
            print(f"There is a current position... \n"
                f"Position side: {position_info['positionSide']} \n"
                f"Price: {position_info['entryPrice']} \n"
                f"Quantity: {abs(float(position_info['positionAmt']))}")
            config[input_side]['current_line']['price'] = round_to_tick(float(position_info['entryPrice']), config['tick_size'])
            config[input_side]['current_line']['quantity'] = abs(float(position_info['positionAmt']))
            config[input_side]['current_line']['cost'] = round(config[input_side]['current_line']['price'] * config[input_side]['current_line']['quantity'], 2)
            config[input_side]['current_line']['status'] = 'FILLED'
            config[input_side]['entry_line']['price'] = config[input_side]['current_line']['price']
            config[input_side]['entry_line']['quantity'] = config[input_side]['current_line']['quantity']
            config[input_side]['entry_line']['cost'] = config[input_side]['current_line']['cost']
            config[input_side]['entry_line']['status'] = 'FILLED'

    # getting wallet current balance
    config[input_side]['risk']['wallet_balance_usdt'] = round(next((float(b['balance']) for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0), 2)
    config[input_side]['risk']['risk_amount'] = round(float(config[input_side]['risk']['wallet_balance_usdt']) * (config[input_side]['risk']['percentage']/100), 2)


    if config[input_side]['entry_line']['status'] != 'FILLED':
        #INPUT entry price
        tick_increment = int(abs(math.log10(config['tick_size'])))
        input_price = float(input("Entry Price ($): ") or 0)
        config[input_side]['entry_line']['price'] = round(input_price, tick_increment)
        #INPUT quantity
        entry_q = input(f"Entry Quantity ({config[input_side]['risk']['risk_amount']}$): ") or config[input_side]['risk']['risk_amount']  # getting quantity in USDT
        config[input_side]['entry_line']['quantity'] = round(float(entry_q) / config[input_side]['entry_line']['price'], config['quantity_precision'])  # converting USDT entry to tokens
        config[input_side]['entry_line']['status'] = 'NEW'
        config[input_side]['current_line']['price'] = config[input_side]['entry_line']['price']
        config[input_side]['current_line']['quantity'] = config[input_side]['entry_line']['quantity']
        config[input_side]['current_line']['cost'] = round(config[input_side]['entry_line']['price'] * config[input_side]['entry_line']['quantity'], 2)

    # INPUT grid distance
    config[input_side]['risk']['grid_distance'] = float(input("Grid Distance (2%): ") or 2) # default valur for grid distance is 2%

    # INPUT token increment
    config[input_side]['risk']['quantity_increment'] = float(input("Token Increment (40%): ") or 40) # default increment is 40%

    # INPUT stop_loss_amount
    config[input_side]['risk']['stop_loss_amount'] = float(input(f"Stop Loss Amount ({config[input_side]['risk']['risk_amount']}$): ") or config[input_side]['risk']['risk_amount'])

    file_path = f"ops/{symbol}.json"
    if os.path.exists(file_path):
        xfile = read_config_data(file_path)
        if xfile.get('strategy') == 'THE_LOAD_UNLOAD_GRID':  # Check strategy and update existing file
            xfile.update({
                input_side: config[input_side],
                'symbol': config['symbol'],
                'input_side': config['input_side'],
                'price_precision': config['price_precision'],
                'quantity_precision': config['quantity_precision'],
                'tick_size': config['tick_size'],
                'step_size': config['step_size']
            })
        else:
            xfile = config  # Change the strategy and overwrite with `config`
    else:
        xfile = config  # Create a new file with `config`

    # Write the updated or new configuration to the file
    write_config_data('ops', f"{config['symbol']}.json", xfile)

    return symbol


class LUGrid:
    def __init__(self, symbol):
        self.symbol = symbol # operation code
        self.data_grid = read_config_data(f"ops/{symbol}.json") #reading configuration files


    def post_order(self):
        self.pos_side = self.data_grid['input_side']

        self.generate_grid()

        if self.data_grid[self.pos_side]['entry_line']['status'] != 'FILLED':
            post_limit_order(self.symbol, self.data_grid[self.pos_side]['entry_line'])

        post_grid_order(self.symbol, self.data_grid[self.pos_side]['body_line'])
        post_stop_loss_order(self.symbol, self.data_grid[self.pos_side]['stop_loss_line'])

        if self.data_grid[self.pos_side]['take_profit_line']['enabled']:
            self.generate_take_profit()
            post_take_profit_order(self.symbol, self.data_grid[self.pos_side]['take_profit_line'])

        write_config_data('ops', f"{self.symbol}.json", self.data_grid)


    def attend_message(self, message):
        if message['o']['X'] != 'FILLED': # Skip processing unless the message status is 'FILLED'
            return

        self.pos_side = message['o']['ps']
        transaction_type = self.get_transaction_type(message)

        match transaction_type:
            case "GRID":  # the event taken is in grid including entry transaction
                logging.debug(f"{self.symbol}_{self.pos_side} - LCD - ATTENDING GRID OPERATION... price: {message['o']['p']}, quantity: {message['o']['q']}")
                self.update_current_position()  # read position information at first the position will be same as entry_line

                if self.data_grid[self.pos_side]['unload_line']['enabled']:
                    clean_order(self.symbol, self.data_grid[self.pos_side]['entry_line']['position_side'], 'UNLOAD')  # clean unload order if there is an unload order opened
                    self.generate_unload_order()
                    post_limit_order(self.symbol, self.data_grid[self.pos_side]['unload_line'])

                if self.data_grid[self.pos_side]['take_profit_line']['enabled']:
                    clean_order(self.symbol, self.data_grid[self.pos_side]['entry_line']['position_side'], 'TAKE_PROFIT')
                    self.generate_take_profit()
                    post_take_profit_order(self.symbol, self.data_grid[self.pos_side]['take_profit_line']) # when an entry line is taken, then take profit will be posted

                write_config_data('ops', f"{self.symbol}.json", self.data_grid)

            case "UNLOAD":  # the event is unload
                logging.debug(f"{self.symbol}_{self.pos_side} - LCD - ATTENDING UNLOAD ORDER... price: {message['o']['p']}, quantity: {message['o']['q']}")

                clean_open_orders(self.symbol, self.data_grid[self.pos_side]['entry_line']['position_side'])  # clean all order for the position side
                self.update_current_position()  # read current position
                self.generate_grid()  # generate new grid points
                post_stop_loss_order(self.symbol, self.data_grid[self.pos_side]['stop_loss_line'])
                post_grid_order(self.symbol, self.data_grid[self.pos_side]['body_line'])

                if self.data_grid[self.pos_side]['take_profit_line']['enabled']:
                    self.generate_take_profit()
                    post_take_profit_order(self.symbol, self.data_grid[self.pos_side]['take_profit_line'])

                write_config_data('ops', f"{self.symbol}.json", self.data_grid)

            case "STOP_LOSS":  # the event is stop loss
                logging.debug(f"{self.symbol}_{self.pos_side} - LCD - ATTENDING STOP LOSS ORDER...  price: {message['o']['p']}, quantity: {message['o']['q']}")
                clean_open_orders(self.symbol, self.data_grid[self.pos_side]['entry_line']['position_side'])  # clean all order for the position side
                # close all open orders from list grid

            case "TAKE_PROFIT":  # the event is take profit
                logging.debug(f"{self.symbol}_{self.pos_side} - LCD - ATTENDING TAKE PROFIT ORDER... price: {message['o']['p']}, quantity: {message['o']['q']}")
                clean_open_orders(self.symbol, self.data_grid[self.pos_side]['entry_line']['position_side'])  # clean all order for the position side
                # close all open orders from grid list

            case _:
                logging.warning(f"{self.symbol}_{self.pos_side} No matching operation to attend for {self.symbol}")

    # get transaction type
    def get_transaction_type(self, message):
        transaction_type_mapping = {
            ('LIMIT', 'LONG', 'BUY'): 'GRID',
            ('LIMIT', 'LONG', 'SELL'): 'UNLOAD',
            ('LIMIT', 'SHORT', 'SELL'): 'GRID',
            ('LIMIT', 'SHORT', 'BUY'): 'UNLOAD',
            ('TAKE_PROFIT_MARKET', None, None): 'TAKE_PROFIT',
            ('STOP_MARKET', None, None): 'STOP_LOSS',
        }

        order_type = message['o']['o']
        position_side = message['o'].get('ps')  # Use .get to avoid KeyError if 'ps' is missing
        side = message['o'].get('S')  # Use .get to avoid KeyError if 'S' is missing

        # Use dictionary lookup for transaction type
        return transaction_type_mapping.get((order_type, position_side, side))


    # round price to increment accepted by binance
    def round_to_tick_size(self, price):
        tick_increment = int(abs(math.log10(self.data_grid['tick_size'])))
        return round(price, tick_increment)
    
    # generate the entire grid points, stop loss and take profit
    def generate_grid(self):
        logging.debug(f"{self.symbol} GENERATING DATA_GRID LINES...")
        self.data_grid[self.pos_side]['body_line'] = [] # clean bd line first

        current_price = self.data_grid[self.pos_side]['current_line']["price"]
        current_quantity = self.data_grid[self.pos_side]['current_line']["quantity"]
        
        self.data_grid[self.pos_side]['average_line']['price'] = self.data_grid[self.pos_side]['current_line']["price"]
        self.data_grid[self.pos_side]['average_line']['quantity'] = self.data_grid[self.pos_side]['current_line']["quantity"]

        # set stop loss taking the first point, entry line
        self.data_grid[self.pos_side]['average_line']['sl_distance'] = (self.data_grid[self.pos_side]['risk']['stop_loss_amount'] * 100) / (self.data_grid[self.pos_side]['average_line']['price'] * self.data_grid[self.pos_side]['average_line']['quantity'])
        
        if self.pos_side == 'LONG':
            self.data_grid[self.pos_side]['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid[self.pos_side]['average_line']['price'] - (self.data_grid[self.pos_side]['average_line']['price'] * self.data_grid[self.pos_side]['average_line']['sl_distance'] / 100) )
            self.data_grid[self.pos_side]['stop_loss_line']['distance'] = round((self.data_grid[self.pos_side]['current_line']['price'] - self.data_grid[self.pos_side]['stop_loss_line']['price']) / self.data_grid[self.pos_side]['current_line']['price'],4)
            
        if self.pos_side == 'SHORT':
                self.data_grid[self.pos_side]['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid[self.pos_side]['average_line']['price'] + (self.data_grid[self.pos_side]['average_line']['price'] * self.data_grid[self.pos_side]['average_line']['sl_distance'] / 100))
                self.data_grid[self.pos_side]['stop_loss_line']['distance'] = round((self.data_grid[self.pos_side]['stop_loss_line']['price'] - self.data_grid[self.pos_side]['current_line']['price']) / self.data_grid[self.pos_side]['current_line']['price'],4)

        self.data_grid[self.pos_side]['stop_loss_line']['quantity'] = self.data_grid[self.pos_side]['current_line']['quantity']
        self.data_grid[self.pos_side]['stop_loss_line']['cost'] = self.data_grid[self.pos_side]['current_line']['cost']

        while True:
            # increment as grid distance the price and quantity
            if self.pos_side == 'LONG':
                new_price = current_price * (1 - (self.data_grid[self.pos_side]['risk']['grid_distance'] / 100))
            
            if self.pos_side == 'SHORT':
                new_price = current_price * (1 + (self.data_grid[self.pos_side]['risk']['grid_distance'] / 100))
            
            new_quantity = current_quantity * (1 + (self.data_grid[self.pos_side]['risk']['quantity_increment'] / 100))
            
            # control if the new price is greater or lower than stop loss price, in order to stop generation of posts
            if self.pos_side == 'LONG':
                if self.data_grid[self.pos_side]['stop_loss_line']['price'] > new_price:
                    break
                
            if self.pos_side == 'SHORT':
                if new_price > self.data_grid[self.pos_side]['stop_loss_line']['price']:
                    break
            
            self.data_grid[self.pos_side]['body_line'].append({"label" : len(self.data_grid[self.pos_side]['body_line'])+1,
                                   "side": 'BUY' if self.pos_side == 'LONG' else 'SELL',
                                   "position_side": self.pos_side,
                                   "price" : self.round_to_tick_size(new_price), 
                                   "quantity" : round(new_quantity, self.data_grid['quantity_precision']),
                                   "type": "LIMIT",
                                   "cost" : round(new_price * new_quantity, 2),
                                   })

            # calculate the average price and accumulated quantity if the position is taken
            self.data_grid[self.pos_side]['average_line']['price'] = self.round_to_tick_size( ((self.data_grid[self.pos_side]['average_line']['price'] * self.data_grid[self.pos_side]['average_line']['quantity']) + (new_price * new_quantity)) / (self.data_grid[self.pos_side]['average_line']['quantity'] + new_quantity))
            self.data_grid[self.pos_side]['average_line']['quantity'] = round(self.data_grid[self.pos_side]['average_line']['quantity'] + new_quantity, self.data_grid['quantity_precision'])
            
            self.data_grid[self.pos_side]['average_line']['sl_distance'] = (self.data_grid[self.pos_side]['risk']['stop_loss_amount'] * 100) / (self.data_grid[self.pos_side]['average_line']['price'] *  self.data_grid[self.pos_side]['average_line']['quantity'])
            
            if self.pos_side == 'LONG':
                self.data_grid[self.pos_side]['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid[self.pos_side]['average_line']['price'] - (self.data_grid[self.pos_side]['average_line']['price'] * self.data_grid[self.pos_side]['average_line']['sl_distance'] / 100) )
                self.data_grid[self.pos_side]['stop_loss_line']['distance'] = round((self.data_grid[self.pos_side]['current_line']['price'] - self.data_grid[self.pos_side]['stop_loss_line']['price']) / self.data_grid[self.pos_side]['current_line']['price'],4)
            
            if self.pos_side == 'SHORT':
                self.data_grid[self.pos_side]['stop_loss_line']['price'] = self.round_to_tick_size( self.data_grid[self.pos_side]['average_line']['price'] + (self.data_grid[self.pos_side]['average_line']['price'] * self.data_grid[self.pos_side]['average_line']['sl_distance'] / 100) )
                self.data_grid[self.pos_side]['stop_loss_line']['distance'] = round((self.data_grid[self.pos_side]['stop_loss_line']['price'] - self.data_grid[self.pos_side]['current_line']['price']) / self.data_grid[self.pos_side]['current_line']['price'],4)

            self.data_grid[self.pos_side]['stop_loss_line']['quantity'] = round(self.data_grid[self.pos_side]['stop_loss_line']['quantity'] + new_quantity, self.data_grid['quantity_precision'])
            self.data_grid[self.pos_side]['stop_loss_line']['cost'] = round(self.data_grid[self.pos_side]['stop_loss_line']['cost'] + (new_price * new_quantity), 2)
            
            current_price = new_price
            current_quantity = new_quantity
            
        logging.debug(f"{self.symbol} body_line generated: {self.data_grid[self.pos_side]['body_line']}")
        logging.debug(f"{self.symbol} stop_loss_line generated: {self.data_grid[self.pos_side]['stop_loss_line']}")


    # Calculate the take profit price based on the side
    def generate_take_profit(self):
        price_factor = 1 + (self.data_grid[self.pos_side]['take_profit_line']['distance']/100) if self.data_grid[self.pos_side]['entry_line']['position_side'] == 'LONG' else 1 - (self.data_grid[self.pos_side]['take_profit_line']['distance']/100)
        self.data_grid[self.pos_side]['take_profit_line']['price'] = self.round_to_tick_size(self.data_grid[self.pos_side]['current_line']['price'] * price_factor)
        logging.debug(f"{self.symbol} take_profit_line generated: {self.data_grid[self.pos_side]['take_profit_line']}")

    # generate unload order
    def generate_unload_order(self):
        # Calculate the unload price based on the side (LONG or SHORT)
        price_factor = 1 + (self.data_grid[self.pos_side]['unload_line']['distance']/100) \
            if self.data_grid[self.pos_side]['current_line']['position_side'] == 'LONG' \
            else 1 - (self.data_grid[self.pos_side]['unload_line']['distance']/100)
        self.data_grid[self.pos_side]['unload_line']['price'] = round_to_tick(self.round_to_tick_size(self.data_grid[self.pos_side]['current_line']['price'] * price_factor), self.data_grid['tick_size'])

        # Calculate unload quantity
        self.data_grid[self.pos_side]['unload_line']['quantity'] = round(
            self.data_grid[self.pos_side]['current_line']['quantity'] - self.data_grid[self.pos_side]['entry_line']['quantity'],  # always take the original quantity inserted
            self.data_grid['quantity_precision']
        )

        logging.debug(f"{self.symbol} UNLOAD generated: {self.data_grid[self.pos_side]['unload_line']}")


    # update current position into current line
    def update_current_position(self):
        logging.debug(f"{self.symbol} UPDATING CURRENT POSITION...")
        try:
            response = client.futures_position_information(symbol=self.symbol) # Fetch futures position information
            for position_info in response:
                if position_info['positionSide'] == self.pos_side:  # Skip empty positions if the exchange is in hedge mode the response 2 current position, one is 0
                    self.data_grid[self.pos_side]['current_line']['price'] = round_to_tick(float(position_info['entryPrice']), self.data_grid['tick_size'])
                    self.data_grid[self.pos_side]['current_line']['quantity'] = abs(float(position_info['positionAmt']))
                    self.data_grid[self.pos_side]['current_line']['cost'] = round(self.data_grid[self.pos_side]['current_line']['price'] * self.data_grid[self.pos_side]['current_line']['quantity'], 2)
                    self.data_grid[self.pos_side]['current_line']['position_side'] = position_info['positionSide']
                    logging.debug(f"{self.symbol} Current position from Binance: {position_info}")
                    break  # Exit after finding the first non-empty position
        except Exception as e:
            logging.exception(f"{self.symbol} update_current_position | Error fetching position information: {e}")


