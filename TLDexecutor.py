from functions import TLDGrid
import numpy as np
import math
import json

# Import and create an instance of TLDGrid by passing the JSON file
calc = TLDGrid(config_file='config.json')

# Now the instance variables are loaded from the JSON
print(calc.gridSide)
print(calc.gridDistance)
print(calc.entryPrice)

# You can then proceed to use the generate function
tab = calc.generate()

print(tab)


    