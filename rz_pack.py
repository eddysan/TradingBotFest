
from binance.client import Client



# Reading json file, the json_file_path should include directory + file + .json extension
def read_config_data(json_file_path):
    try:
        # Attempt to load file
        if os.path.isfile(json_file_path):
            with open(json_file_path, 'r') as file:
                config_file = json.load(file)
                logging.debug(f"Successfully loaded data_grid file: {json_file_path}")
                return config_file
        else:
            logging.warning(f"data_grid file '{json_file_path}' not found")
    except (FileNotFoundError, KeyError):
        logging.exception("Error: Invalid config.json file or not found. Please check the file path and format.")
        print(f"Error: Invalid {json_file_path} file or not found. Please check the file path and format.")
        return

# Writting json data grid file
def write_config_data(directory, file_name, data_grid):
    os.makedirs(directory, exist_ok=True) # if directory doesn't exist, it will be created
    xfile = f"{directory}/{file_name}" # file name should have extension to
    with open(xfile, 'w') as file:
        json.dump(data_grid, file, indent=4)  # Pretty-print JSON
    return None
