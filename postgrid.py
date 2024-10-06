from functions import *
from binance.client import Client

# status for each instance of bot
status = 'ORDER'

# load default config from json
data_grid = load_config('config.json')

# Set up authentication
binance_config_file = load_config('../credentials.json')  
api_key = binance_config_file['api_key']
api_secret = binance_config_file['api_secret']

client = Client(api_key, api_secret)

# getting account balance from the wallet and set compound amount to 10% of the account
data_grid['sl_compound'] = round(float(get_account_balance(client)) * 0.10, 2)

# fills external data from terminal
data_grid = get_external_data(client, data_grid)


# default variables to dev
#data_grid['token_pair'] = 'NEIROUSDT'
#data_grid['grid_side'] = 'LONG'
#data_grid['grid_distance'] = 0.02
#data_grid['token_increment'] = 0.40
#data_grid['sl_amount'] = 10.00
#data_grid['entry_price'] = 0.0011000
#data_grid['entry_quantity'] = 9090


# You can then proceed to use the generate function
data_grid = generate(data_grid)
#print(data_grid)
    

#data_grid['entry_order'] = post_order(client, data_grid, 'entry_order')
#print(data_grid)

data_grid['body_order'] = post_order(client, data_grid,'body_order')
#print(data_grid)

#data_grid['sl_order'] = post_stop_loss_order(client, data_grid)

