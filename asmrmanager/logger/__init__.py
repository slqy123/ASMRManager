import logging
from logging.handlers import TimedRotatingFileHandler
from os import makedirs, environ
from sys import stderr

from colorlog import ColoredFormatter

from asmrmanager.filemanager.appdirs_ import LOG_PATH

LOG_LEVEL = logging.DEBUG if environ.get("ASMR_DEBUG") else logging.INFO

log_path = LOG_PATH
makedirs(log_path, exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

console_formatter = ColoredFormatter(
    "%(asctime)s - %(log_color)s%(levelname)s%(reset)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    reset=True,
)

file_formatter = logging.Formatter(
    "%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console_handler = logging.StreamHandler(stderr)
console_handler.setLevel(LOG_LEVEL)
console_handler.setFormatter(console_formatter)

file_handler = TimedRotatingFileHandler(
    log_path / "asmr.log",
    when="D",
    backupCount=1,
    encoding="utf8",
)
file_handler.setLevel(LOG_LEVEL)
file_handler.setFormatter(file_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)
