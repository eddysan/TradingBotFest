import numpy as np
import json
from binance.client import Client
import requests


# load a json config
def load_config(json_file):
    try:
        # Load the JSON file with default config
        with open(json_file, 'r') as file:
            data = json.load(file)
    except Exception as e:
        print(f"Error loading configuration: {e}")
    return data

# Function to get Binance server time
def get_binance_server_time():
    response = requests.get('https://api.binance.com/api/v3/time')
    if response.status_code == 200:
        return response.json()['serverTime']
    else:
        raise Exception(f"Failed to fetch server time. Response: {response.text}")


# generate the entire grid entry points as price, tokens and cost
def generate(data_grid):
    lost_amount = 0
    new_price = 0
    sl_amount = data_grid['sl_amount']
    current_price = data_grid["entry_price"]
    current_token = data_grid["entry_quantity"]
    new_distance = data_grid['grid_distance']

    # percentage array for every entry
    p = np.array([0.0])

    # cost array for every entry
    k = np.array([[ data_grid['entry_price'] * data_grid['entry_quantity'] ]])

    data_grid['entry_order'].append({"g_entry" : 0, "g_price" : round(data_grid['entry_price'],data_grid['price_decimal']), "g_quantity" : round(data_grid['entry_quantity'],data_grid['quantity_decimal']), "g_cost" : round(data_grid['entry_price'] * data_grid['entry_quantity'],data_grid['price_decimal'])})

    while lost_amount <= sl_amount:
  
        lost_amount = np.dot(p,k).item()
        # increment the percentage
        p = p + 0.001
  
        # look for multiple for percentage in order to add new element
        if round(p[0].item(),4) == round(new_distance,4):
            # start new percentage for new entry
            p = np.append(p,[0.0000])

            if data_grid['grid_side'] == 'LONG':
                new_price = current_price * (1 - data_grid['grid_distance'])
            elif data_grid['grid_side'] == 'SHORT':
                new_price = current_price * (1 + data_grid['grid_distance'])

            # Calcular la nueva cantidad de tokens a comprar en la recompra
            new_token = current_token * (1 + data_grid['token_increment'])

            # appends new tuple to the array for new entry
            k = np.append(k,[[new_price * new_token]], axis=0)

            # update to list
            data_grid['body_order'].append({"g_entry" : len(data_grid['body_order'])+1, "g_price" : round(new_price,data_grid['price_decimal']), "g_quantity" : round(new_token,data_grid['quantity_decimal']), "g_cost" : round(new_price * new_token, data_grid['price_decimal'])})

            # update price and tokens to new
            current_price = new_price
            current_token = new_token
            new_distance = new_distance + data_grid['grid_distance'] 

    if data_grid['grid_side'] == 'LONG':
        sl_price = data_grid['entry_price'] * (1 - p[0].item())
    elif data_grid['grid_side'] == 'SHORT':
        sl_price = data_grid['entry_price'] * (1 + p[0].item())

    data_grid['sl_order'].append({"g_entry" : len(data_grid['body_order'])+1, "g_price" : round(sl_price, data_grid['price_decimal']), "g_quantity" : round(current_token, data_grid['quantity_decimal']), "g_cost" : round(sl_price * current_token, data_grid['price_decimal'])})

    return data_grid


# post a open position for 
def post_order(data_grid, branch):
    order_data = data_grid[branch]
    new_order = []
  
    # Set up authentication
    binance_config_file = load_config('../credentials.json')  
    api_key = binance_config_file['api_key']
    api_secret = binance_config_file['api_secret']
    
    client = Client(api_key, api_secret)
    
    for order in order_data:
        
        response = client.futures_create_order(
            symbol = data_grid['token_pair'].upper(),
            side = 'BUY' if data_grid['grid_side'] == 'LONG' else 'SELL',
            type = 'LIMIT',
            timeInForce = 'GTC',
            positionSide = data_grid['grid_side'],
            price = str(order['g_price']),
            quantity = str(order['g_quantity'])
            )
        new_order.append(order | response)
    
    
        # must add the result to grid
    return new_order


