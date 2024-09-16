import numpy as np
import json
import math

side = 'sell'
grid_distance = 0.02
token_increment_percentage = 0.40
stop_loss_amount = 10
entry_price = 0.0074000
entry_tokens_amount = 1351

current_price = entry_price
current_tokens = entry_tokens_amount
new_distance = grid_distance

percentage = 0
lost_amount = 0
p = np.array([0])
k = np.array([[entry_price * entry_tokens_amount]])

dt = [{"entry" : 0, "price" : entry_price, "tokens" : entry_tokens_amount, "cost" : entry_price * entry_tokens_amount}]

while lost_amount <= stop_loss_amount:
  
  lost_amount = np.dot(p,k).item()
  # increment the percentage
  p = p + 0.0001
  
  # look for multiple for percentage in order to add new element
  if round(p[0].item(),4) == round(new_distance,4):
    # start new percentage for new entry
    p = np.append(p,[0.0000])

    if side == 'buy':
      new_price = current_price * (1 - grid_distance)
    elif side == 'sell':
      new_price = current_price * (1 + grid_distance)

    # Calcular la nueva cantidad de tokens a comprar en la recompra
    new_tokens = current_tokens * (1 + token_increment_percentage)

    # appends new tuple to the array for new entry
    k = np.append(k,[[new_price * new_tokens]], axis=0)

    # update to list
    dt.append({"entry" : len(dt), "price" : new_price, "tokens" : new_tokens, "cost" : new_price * new_tokens})

    # update price and tokens to new
    current_price = new_price
    current_tokens = new_tokens
    new_distance = new_distance + grid_distance 

  if side == 'buy':
    stop_loss_price = entry_price * (1 - p[0].item())
  elif side == 'sell':
    stop_loss_price = entry_price * (1 + p[0].item())

print(dt)
print("lost: " + str(lost_amount))
print("perecentage: " + str(p[0].item()))
print("SL price: " + str(stop_loss_price))