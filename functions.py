import numpy as np
import json
import math
from binance.client import Client
import base64
import requests
import time
from cryptography.hazmat.primitives.serialization import load_pem_private_key

class TLDGrid:

  def generate(self, grid_side, grid_distance, token_increment, sl_amount, entry_price, entry_token):
    percentage = 0
    lost_amount = 0
    new_price = 0
    current_price = entry_price
    current_token = entry_token
    new_distance = grid_distance

    # percentage array for every entry
    p = np.array([0.0])

    # cost array for every entry
    k = np.array([[entry_price * entry_token]])

    dt = [{"entry" : 0, "price" : entry_price, "tokens" : entry_token, "cost" : entry_price * entry_token}]

    while lost_amount <= sl_amount:
  
      lost_amount = np.dot(p,k).item()
      # increment the percentage
      p = p + 0.001
  
      # look for multiple for percentage in order to add new element
      if round(p[0].item(),4) == round(new_distance,4):
        # start new percentage for new entry
        p = np.append(p,[0.0000])

        if grid_side == 'long':
          new_price = current_price * (1 - grid_distance)
        elif grid_side == 'short':
          new_price = current_price * (1 + grid_distance)

        # Calcular la nueva cantidad de tokens a comprar en la recompra
        new_token = current_token * (1 + token_increment)

        # appends new tuple to the array for new entry
        k = np.append(k,[[new_price * new_token]], axis=0)

        # update to list
        dt.append({"entry" : len(dt), "price" : new_price, "tokens" : new_token, "cost" : new_price * new_token})

        # update price and tokens to new
        current_price = new_price
        current_token = new_token
        new_distance = new_distance + grid_distance 

    if grid_side == 'long':
      sl_price = entry_price * (1 - p[0].item())
    elif grid_side == 'short':
      sl_price = entry_price * (1 + p[0].item())
  
    return dt


def load_config():
  try:
    # Load the JSON file
    with open('config.json', 'r') as file:
      data = json.load(file)
  except Exception as e:
    print(f"Error loading configuration: {e}")
  return data


# ---


config_file = load_config()

# try input and apply default values
#gridSide = input("Grid Side (long/short): ") or 'long'
#gridDistance = float(input("Grid Distance (%): ") or 2) / 100
#tokenIncrement = float(input("Token Incrementv (%): ") or 40) / 100
#SLAmount = float(input("Stop Loss Amount (USDT): ") or 10)
#entryPrice = float(input("Entry Price: ") or 0)
#entryToken = float(input("Entry Token: ") or 0)

# default variables to dev
grid_side = 'long'
grid_distance = 0.02
token_increment = 0.40
sl_amount = 10.00
entry_price = 0.3200
entry_token = 31

# Import and create an instance of TLDGrid by passing the JSON file
calc = TLDGrid()

# You can then proceed to use the generate function
tab = calc.generate(grid_side, grid_distance, token_increment, sl_amount, entry_price, entry_token)


# ED25519 Keys
#apiKey = "wmofsFgVdJjppz09nNoMe5JVxOpU3TM7NNq5eSfJm0MGo3PoW196CY6BtOCRN5DF"
#privateKey = "MC4CAQAwBQYDK2VwBCIEII7CkdD8SF5EtHogmn5Ktiluc+cEsp0GakkJwDBpb8QA"
#privateKeyPass = "<password_if_applicable>"

# Set up authentication
API_KEY='WEBNFwxVcuFvNc3xEz7zlRyLbDBuNLIr0ZqzKh2sncCV9PKKVm8Kt9kKEndZW27O'
PRIVATE_KEY_PATH='binance_private_key.txt'

# Load the private key.
# In this example the key is expected to be stored without encryption,
# but we recommend using a strong password for improved security.
with open(PRIVATE_KEY_PATH, 'rb') as f:
  private_key = load_pem_private_key(data=f.read(), password=None)

# Set up the request parameters
params = {
    'symbol':       'ETHUSDT',
    'side':         'BUY',
    'type':         'LIMIT',
    'timeInForce':  'GTC',
    'quantity':     '0.009',
    'price':        '2300',
    'dualSidePosition': True,
    'positionSide': 'LONG'
}

# Timestamp the request
timestamp = int(time.time() * 1000) # UNIX timestamp in milliseconds
params['timestamp'] = timestamp

# Sign the request
payload = '&'.join([f'{param}={value}' for param, value in params.items()])
signature = base64.b64encode(private_key.sign(payload.encode('ASCII')))
params['signature'] = signature

# Send the request
headers = {
    'X-MBX-APIKEY': API_KEY,
}
response = requests.post(
    'https://fapi.binance.com/fapi/v1/order',
    headers=headers,
    data=params,
)
print(response.json())


#with open(privateKey, 'rb') as f:
#    privateKey = f.read()

#client = Client(api_key=apiKey, private_key=privateKey)


# Now the instance variables are loaded from the JSON
#print(calc.gridSide)
#print(calc.gridDistance)
#print(calc.entryPrice)

#print(tab)


    