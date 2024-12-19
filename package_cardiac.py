from package_common import *
from package_connection import client

# input data from console
def input_data():
    logging.debug(f"INPUT DATA...")
    config = read_config_data(f"config/cardiac.config") #reading config file

    # INPUT symbol
    config['symbol'] = input("Symbol (BTC): ").upper() + "USDT"
    SYMBOL = config.get('symbol')

    # INPUT side (default to LONG)
    config['input_side'] = input("Side (LONG|SHORT): ").upper() or "LONG"
    POS_SIDE = config['input_side']

    # Fetch info if there is a current position
    response = client.futures_position_information(symbol=SYMBOL)

    # Loop through the list to find the relevant position based on 'positionSide'
    for position_info in response:
        if float(position_info['positionAmt']) != 0 and position_info['positionSide'] == config['input_side']:  # if position amount is not zero, then there is a current position
            print(f"There is a current position... \n"
                f"Position side: {position_info['positionSide']} \n"
                f"Price: {position_info['entryPrice']} \n"
                f"Quantity: {abs(float(position_info['positionAmt']))}")
            config[POS_SIDE]['entry_line']['price'] = float(position_info['entryPrice'])
            config[POS_SIDE]['entry_line']['quantity'] = abs(float(position_info['positionAmt']))
            config[POS_SIDE]['entry_line']['status'] = 'FILLED'

    # getting wallet current balance
    config[POS_SIDE]['risk']['wallet_balance_usdt'] = round(next((float(b['balance']) for b in client.futures_account_balance() if b["asset"] == "USDT"), 0.0), 2)
    config[POS_SIDE]['risk']['amount'] = round(float(config[POS_SIDE]['risk']['wallet_balance_usdt']) * (config[POS_SIDE]['risk']['percentage']/100), 2)

    # Getting precisions for the symbol
    info = client.futures_exchange_info()['symbols']
    symbol_info = next((x for x in info if x['symbol'] == SYMBOL), None)
    
    # Retrieve precision filter 
    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            config['step_size'] = float(f['stepSize'])
        elif f['filterType'] == 'PRICE_FILTER':
            config['tick_size'] = float(f['tickSize'])
    
    config['price_precision'] = symbol_info['pricePrecision']
    config['quantity_precision'] = symbol_info['quantityPrecision']

    # INPUT entry price and quantity
    if config[POS_SIDE]['entry_line']['status'] != 'FILLED':
        # INPUT entry price
        tick_increment = int(abs(math.log10(config['tick_size'])))
        config[POS_SIDE]['entry_line']['price'] = round(float(input("Entry Price ($): ")), tick_increment)
        # INPUT quantity
        entry_token = round(float(config[POS_SIDE]['risk']['amount']) / config[POS_SIDE]['entry_line']['price'], config['quantity_precision'])  # converting compound amount to tokens
        config[POS_SIDE]['entry_line']['quantity'] = float(input(f"Entry Quantity ({entry_token} {config['symbol'][:-4]}): ") or entry_token)  # getting quantity in USDT
        config[POS_SIDE]['entry_line']['status'] = 'NEW'

    # INPUT stop_loss_amount
    config[POS_SIDE]['risk']['stop_loss_amount'] = float(input(f"Stop Loss Amount ({config[POS_SIDE]['risk']['amount']}$): ") or config[POS_SIDE]['risk']['amount'])

    if os.path.exists(f"ops/{config['symbol']}.json"):
        xfile = read_config_data(f"ops/{config['symbol']}.json")
        if xfile['strategy'] == 'CARDIAC': #update existing file
            xfile[POS_SIDE] = config[POS_SIDE]
            xfile['symbol'] = SYMBOL
            xfile['input_side'] = config['input_side']
            xfile['price_precision'] = config['price_precision']
            xfile['quantity_precision'] = config['quantity_precision']
            xfile['tick_size'] = config['tick_size']
            xfile['step_size'] = config['step_size']
            write_config_data('ops', f"{config['symbol']}.json", xfile)
        else:
            write_config_data('ops', f"{config['symbol']}.json", config) #change strategy
    else: #if file does't exist then create one
        write_config_data('ops', f"{config['symbol']}.json", config)

    if config[POS_SIDE]['entry_line']['status'] == 'FILLED':
        msg = {"o":{"ps":config[POS_SIDE]['entry_line']['position_side']}}
        car = CardiacGrid(config['symbol'])
        car.attend_message(msg)
        return None

    return config['symbol']


class CardiacGrid:
    
    def __init__(self, symbol):
        self.symbol = symbol #getting operation symbol to read file
        self.data_grid = read_config_data(f"ops/{self.symbol}.json") # reading config file

    # post input orders
    def post_order(self):
        self.side = self.data_grid.get('input_side')
        post_limit_order(self.symbol, self.data_grid[self.side]['entry_line'])
        write_config_data('ops',f"{self.symbol}.json",self.data_grid)

    # attend messages from web socket
    def attend_message(self, message):
        if message['o']['X'] != 'FILLED': # Skip processing unless the message status is 'FILLED'
            return

        self.pos_side = message['o']['ps'] #getting position side
        clean_open_orders(self.symbol, self.pos_side)  # clean all open orders
        self.update_current_position()  # update current position to current_line

        if self.data_grid[self.pos_side]['current_line']['quantity'] != 0: #if the operation is in market and position ends to zero
            if self.data_grid[self.pos_side]['stop_loss_line']['enabled']:
                self.generate_stop_loss()
                post_stop_loss_order(self.symbol, self.data_grid[self.pos_side]['stop_loss_line'])

            if self.data_grid[self.pos_side]['unload_line']['enabled']:
                self.generate_unload()
                post_limit_order(self.symbol, self.data_grid[self.pos_side]['unload_line'])

            if self.data_grid[self.pos_side]['take_profit_line']['enabled']:
                self.generate_take_profit()
                post_take_profit_order(self.symbol, self.data_grid[self.pos_side]['take_profit_line'])

        write_config_data("ops", f"{self.symbol}.json", self.data_grid)


    # round price to increment accepted by binance
    def round_to_tick_size(self, price):
        tick_increment = int(abs(math.log10(self.data_grid['tick_size'])))
        return round(price, tick_increment)
    

    # update current position from binance
    def update_current_position(self):
        logging.info(f"{self.symbol} - UPDATING CURRENT POSITION...")
        try:
            response = client.futures_position_information(symbol=self.symbol) # Fetch futures position information
            position_info = next((pos for pos in response if pos['positionSide'] == self.pos_side),None)

            if position_info:
                entry_price = float(position_info['entryPrice'])
                position_amount = abs(float(position_info['positionAmt']))
                self.data_grid[self.pos_side]['current_line']['price'] = self.round_to_tick_size(entry_price)
                self.data_grid[self.pos_side]['current_line']['quantity'] = round(position_amount, self.data_grid['quantity_precision'])
                logging.debug(f"{self.symbol} Current position from Binance: {position_info}")
            else:
                logging.info(f"{self.symbol} - No relevant position found for side: {self.pos_side}")

        except Exception as e:
            logging.exception(f"{self.symbol} Failed to update position information: {e}")

    # generate the entire grid points, stop loss and take profit
    def generate_stop_loss(self):
        logging.info(f"{self.symbol} - GENERATING STOP_LOSS DATA...")
        try:
            # set stop loss taking the first point, entry line
            self.data_grid[self.pos_side]['current_line']['distance'] = (self.data_grid[self.pos_side]['risk']['stop_loss_amount'] * 100) / (self.data_grid[self.pos_side]['current_line']['price'] * self.data_grid[self.pos_side]['current_line']['quantity'])
        
            if self.data_grid[self.pos_side]['stop_loss_line']['position_side'] == 'LONG':
                self.data_grid[self.pos_side]['stop_loss_line']['price'] = abs(self.round_to_tick_size( float(self.data_grid[self.pos_side]['current_line']['price'] - (self.data_grid[self.pos_side]['current_line']['price'] * self.data_grid[self.pos_side]['current_line']['distance'] / 100) )))
                self.data_grid[self.pos_side]['stop_loss_line']['distance'] = round((self.data_grid[self.pos_side]['current_line']['price'] - self.data_grid[self.pos_side]['stop_loss_line']['price']) / self.data_grid[self.pos_side]['current_line']['price'],4)

            if self.data_grid[self.pos_side]['stop_loss_line']['position_side'] == 'SHORT':
                self.data_grid[self.pos_side]['stop_loss_line']['price'] = abs(self.round_to_tick_size(float(self.data_grid[self.pos_side]['current_line']['price'] + (self.data_grid[self.pos_side]['current_line']['price'] * self.data_grid[self.pos_side]['current_line']['distance'] / 100) )))
                self.data_grid[self.pos_side]['stop_loss_line']['distance'] = round((self.data_grid[self.pos_side]['stop_loss_line']['price'] - self.data_grid[self.pos_side]['current_line']['price']) / self.data_grid[self.pos_side]['current_line']['price'],4)

            self.data_grid[self.pos_side]['stop_loss_line']['quantity'] = self.data_grid[self.pos_side]['current_line']['quantity']
            logging.debug(f"{self.symbol}_{self.data_grid[self.pos_side]['stop_loss_line']['position_side']} stop_loss_line generated: {self.data_grid[self.pos_side]['stop_loss_line']}")

        except Exception as e:
            logging.debug(f"{self.symbol} Error generating stop loss data: {e}")
            

    # generate take profit line
    def generate_take_profit(self):
        try:
            price_factor = 1 + (self.data_grid[self.pos_side]['take_profit_line']['distance']/100) if self.data_grid[self.pos_side]['take_profit_line']['position_side'] == 'LONG' else 1 - (self.data_grid[self.pos_side]['take_profit_line']['distance']/100)
            self.data_grid[self.pos_side]['take_profit_line']['price'] = self.round_to_tick_size(self.data_grid[self.pos_side]['current_line']['price'] * price_factor)
            logging.debug(f"{self.symbol}_{self.data_grid[self.pos_side]['take_profit_line']['position_side']} take_profit_line generated: {self.data_grid[self.pos_side]['take_profit_line']}")

        except Exception as e:
            logging.debug(f"{self.symbol}_{self.data_grid[self.pos_side]['take_profit_line']['position_side']} Error generating take profit line: {e}")


    # generate unload line
    def generate_unload(self):
        try:
            price_factor = 1 + (self.data_grid[self.pos_side]['unload_line']['distance']/100) if self.data_grid[self.pos_side]['unload_line']['position_side'] == 'LONG' else 1 - (self.data_grid[self.pos_side]['unload_line']['distance']/100)
            self.data_grid[self.pos_side]['unload_line']['price'] = self.round_to_tick_size(self.data_grid[self.pos_side]['current_line']['price'] * price_factor)
            # Calculate unload quantity
            self.data_grid[self.pos_side]['unload_line']['quantity'] = round(
                self.data_grid[self.pos_side]['current_line']['quantity'] - self.data_grid[self.pos_side]['entry_line']['quantity'], # always take the original quantity inserted
                self.data_grid['quantity_precision']
                    )

            logging.debug(f"{self.symbol}_{self.data_grid[self.pos_side]['unload_line']['position_side']} unload_line to post: {self.data_grid[self.pos_side]['unload_line']}")

        except Exception as e:
            logging.debug(f"{self.symbol}_{self.data_grid[self.pos_side]['unload_line']['position_side']} Error generating unload line: {e}")

