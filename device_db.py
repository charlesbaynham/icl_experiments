import importlib

import device_db_config

# Force reload of the module in case it has been updated
importlib.reload(device_db_config)
device_db = device_db_config.get_device_db()
