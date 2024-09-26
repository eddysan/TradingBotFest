#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Sep 22 23:07:58 2024

@author: eddysan
"""

import base64
import time
import json
import requests
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from websocket import create_connection


# Function to get Binance server time
def get_binance_server_time():
    response = requests.get('https://api.binance.com/api/v3/time')
    if response.status_code == 200:
        return response.json()['serverTime']
    else:
        raise Exception(f"Failed to fetch server time. Response: {response.text}")

# Set up authentication
API_KEY = '9moGAdDl4pkFCWb69qU5B8fCWJ24p32lnmMMX6kHSwuPSwy9nuwkrnxoNX6msa1P'
PRIVATE_KEY_PATH = '../binance_private_key.txt'

# Load the private key.
# In this example the key is expected to be stored without encryption,
# but we recommend using a strong password for improved security.
with open(PRIVATE_KEY_PATH, 'rb') as f:
    private_key = load_pem_private_key(data=f.read(), password=None)

# Set up the request parameters
params = {
    'apiKey':        API_KEY,
    'symbol':       'ETHUSDT',
    'side':         'BUY',
    'type':         'LIMIT',
    'timeInForce':  'GTC',
    'dualSidePosition': True,
    'quantity':     '0.008',
    'price':        '2570'
}

# Timestamp the request
#timestamp = int(time.time() * 1000) # UNIX timestamp in milliseconds
#params['timestamp'] = timestamp
params['timestamp'] = get_binance_server_time()
params['recvWindow'] = 5000

# Sign the request
payload = '&'.join([f'{param}={value}' for param, value in sorted(params.items())])

signature = base64.b64encode(private_key.sign(payload.encode('ASCII')))
params['signature'] = signature.decode('ASCII')

# Send the request
request = {
    'id': 'my_new_order',
    'method': 'order.place',
    'params': params
}

ws = create_connection("wss://ws-fapi.binance.com/ws-fapi/v1")
ws.send(json.dumps(request))
result =  ws.recv()
ws.close()

print(result)
