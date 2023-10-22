from pathlib import Path

import appdirs

from asmrmanager import __name__ as package_name

CACHE_PATH = Path(appdirs.user_cache_dir(package_name))
CONFIG_PATH = Path(appdirs.user_config_dir(package_name))
DATA_PATH = Path(appdirs.user_data_dir(package_name))
LOG_PATH = Path(appdirs.user_log_dir(package_name))
