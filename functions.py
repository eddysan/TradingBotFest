import numpy as np
import json
#import math
#from binance.client import Client
import base64
import requests
#from websocket import create_connection
#import time
from cryptography.hazmat.primitives.serialization import load_pem_private_key


# load json with default data, this json represent the entire grid for operations
def load_config():
  try:
    # Load the JSON file with default config
    with open('config.json', 'r') as file:
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
  current_token = data_grid["entry_token"]
  new_distance = data_grid['grid_distance']

  # percentage array for every entry
  p = np.array([0.0])

  # cost array for every entry
  k = np.array([[ data_grid['entry_price'] * data_grid['entry_token'] ]])

  data_grid['entry_order'].append({"entry" : 0, "price" : data_grid['entry_price'], "tokens" : data_grid['entry_token'], "cost" : data_grid['entry_price'] * data_grid['entry_token']})

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
      data_grid['body_order'].append({"entry" : len(data_grid['body_order'])+1, "price" : new_price, "tokens" : new_token, "cost" : new_price * new_token})

      # update price and tokens to new
      current_price = new_price
      current_token = new_token
      new_distance = new_distance + data_grid['grid_distance'] 

  if data_grid['grid_side'] == 'LONG':
    sl_price = data_grid['entry_price'] * (1 - p[0].item())
  elif data_grid['grid_side'] == 'SHORT':
    sl_price = data_grid['entry_price'] * (1 + p[0].item())

  data_grid['sl_order'].append({"entry" : len(data_grid['body_order'])+1, "price" : sl_price, "tokens" : current_token, "cost" : sl_price * current_token})

  return data_grid


def post_order(order_data):
  
  # Set up authentication
  API_KEY='9moGAdDl4pkFCWb69qU5B8fCWJ24p32lnmMMX6kHSwuPSwy9nuwkrnxoNX6msa1P'
  PRIVATE_KEY_PATH='../binance_private_key.txt'

  # Load the private key.
  # In this example the key is expected to be stored without encryption,
  # but we recommend using a strong password for improved security.
  with open(PRIVATE_KEY_PATH, 'rb') as f:
    private_key = load_pem_private_key(data=f.read(), password=None)

  # setting parameters for request
    params = {
      'symbol':       data_grid['token_pair'].upper(),
      'side':         'BUY' if data_grid['grid_side'] == 'LONG' else 'SELL',
      'type':         'LIMIT',
      'timeInForce':  'GTC',
      'dualSidePosition': True,
      'positionSide': data_grid['grid_side']
    }
  
  # Timestamp the request
  #timestamp = int(time.time() * 5000) # UNIX timestamp in milliseconds
  params['timestamp'] = get_binance_server_time()
  params['recvWindow'] = 10000

  # Sign the request
  payload = '&'.join([f'{param}={value}' for param, value in params.items()])
  signature = base64.b64encode(private_key.sign(payload.encode('ASCII')))
  params['signature'] = signature.decode('ASCII')

  # Send the request
  headers = {
      'X-MBX-APIKEY': API_KEY,
  }

  for order in order_data:
    # Set up the request parameters
    params['quantity'] = str(order['tokens'])
    params['price'] = str(order['price'])

    response = requests.post(
      'https://fapi.binance.com/fapi/v1/order',
      headers=headers,
      data=params,
    )

    # must add the result to grid
    order_data.append(response)
    print(response)
    return order_data


data_grid = load_config()

# try input and apply default values
#gridSide = input("Grid Side (long/short): ") or 'long'
#gridDistance = float(input("Grid Distance (%): ") or 2) / 100
#tokenIncrement = float(input("Token Incrementv (%): ") or 40) / 100
#SLAmount = float(input("Stop Loss Amount (USDT): ") or 10)
#entryPrice = float(input("Entry Price: ") or 0)
#entryToken = float(input("Entry Token: ") or 0)

# default variables to dev
data_grid['token_pair'] = 'ADAUSDT'
data_grid['grid_side'] = 'LONG'
data_grid['grid_distance'] = 2 /100
data_grid['token_increment'] = 40 / 100
data_grid['sl_amount'] = 10.00
data_grid['entry_price'] = 0.3270
data_grid['entry_token'] = 28


# You can then proceed to use the generate function
data_grid = generate(data_grid)

data_grid['entry_order'] = post_order(data_grid['entry_order'])
print(data_grid)

data_grid['body_order'] = post_order(data_grid['body_order'])
print(data_grid)

# ED25519 Keys
#apiKey = "wmofsFgVdJjppz09nNoMe5JVxOpU3TM7NNq5eSfJm0MGo3PoW196CY6BtOCRN5DF"
#privateKey = "MC4CAQAwBQYDK2VwBCIEII7CkdD8SF5EtHogmn5Ktiluc+cEsp0GakkJwDBpb8QA"
#privateKeyPass = "<password_if_applicable>"


#with open(privateKey, 'rb') as f:
#    privateKey = f.read()

#client = Client(api_key=apiKey, private_key=privateKey)


# Now the instance variables are loaded from the JSON
#print(calc.gridSide)
#print(calc.gridDistance)
#print(calc.entryPrice)

#print(tab)


    