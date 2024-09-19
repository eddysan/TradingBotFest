import numpy as np
import json
import math

class TLDGrid:

  def generate(self, gridSide, gridDistance, tokenIncrement, SLAmount, entryPrice, entryToken):
    percentage = 0
    lostAmount = 0
    newPrice = 0
    currentPrice = entryPrice
    currentToken = entryToken
    newDistance = gridDistance

    # percentage array for every entry
    P = np.array([0.0])

    # cost array for every entry
    K = np.array([[entryPrice * entryToken]])

    dt = [{"entry" : 0, "price" : entryPrice, "tokens" : entryToken, "cost" : entryPrice * entryToken}]

    while lostAmount <= SLAmount:
  
      lostAmount = np.dot(P,K).item()
      # increment the percentage
      P = P + 0.001
  
      # look for multiple for percentage in order to add new element
      if round(P[0].item(),4) == round(newDistance,4):
        # start new percentage for new entry
        P = np.append(P,[0.0000])

        if gridSide == 'long':
          newPrice = currentPrice * (1 - gridDistance)
        elif gridSide == 'short':
          newPrice = currentPrice * (1 + gridDistance)

        # Calcular la nueva cantidad de tokens a comprar en la recompra
        newToken = currentToken * (1 + tokenIncrement)

        # appends new tuple to the array for new entry
        K = np.append(K,[[newPrice * newToken]], axis=0)

        # update to list
        dt.append({"entry" : len(dt), "price" : newPrice, "tokens" : newToken, "cost" : newPrice * newToken})

        # update price and tokens to new
        currentPrice = newPrice
        currentToken = newToken
        newDistance = newDistance + gridDistance 

    if gridSide == 'long':
      SLPrice = entryPrice * (1 - P[0].item())
    elif gridSide == 'short':
      SLPrice = entryPrice * (1 + P[0].item())
  
    return dt


def loadConfig():
  try:
    # Load the JSON file
    with open('config.json', 'r') as file:
      data = json.load(file)
  except Exception as e:
    print(f"Error loading configuration: {e}")
  return data


# ---


configFile = loadConfig()

# try input and apply default values
#gridSide = input("Grid Side (long/short): ") or 'long'
#gridDistance = float(input("Grid Distance (%): ") or 2) / 100
#tokenIncrement = float(input("Token Incrementv (%): ") or 40) / 100
#SLAmount = float(input("Stop Loss Amount (USDT): ") or 10)
#entryPrice = float(input("Entry Price: ") or 0)
#entryToken = float(input("Entry Token: ") or 0)

# default variables to dev
gridSide = 'long'
gridDistance = 0.02
tokenIncrement = 0.40
SLAmount = 10.00
entryPrice = 0.3200
entryToken = 31

# Import and create an instance of TLDGrid by passing the JSON file
calc = TLDGrid()

# You can then proceed to use the generate function
tab = calc.generate(gridSide, gridDistance, tokenIncrement, SLAmount, entryPrice, entryToken)

# Now the instance variables are loaded from the JSON
#print(calc.gridSide)
#print(calc.gridDistance)
#print(calc.entryPrice)

print(tab)


    