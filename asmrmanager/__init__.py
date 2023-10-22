from pathlib import Path
import appdirs

CACHE_PATH = Path(appdirs.user_cache_dir(__name__))
CONFIG_PATH = Path(appdirs.user_config_dir(__name__))
DATA_PATH = Path(appdirs.user_data_dir(__name__))
LOG_PATH = Path(appdirs.user_log_dir(__name__))

from asmrmanager.filemanager.manager import FileManager

if not (DATA_PATH / 'sqls').exists():
    FileManager.init_sqls()

if not (CONFIG_PATH / 'config.toml').exists():
    FileManager.init_config()