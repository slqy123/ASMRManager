from asmrmanager.filemanager.appdirs_ import CONFIG_PATH, DATA_PATH
from asmrmanager.filemanager.manager import FileManager

if not (DATA_PATH / "sqls").exists():
    FileManager.init_sqls()

if not (CONFIG_PATH / "config.toml").exists():
    FileManager.init_config()
