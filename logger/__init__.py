from sys import stdout
import logging
from colorlog import ColoredFormatter
from logging.handlers import TimedRotatingFileHandler
from os import makedirs

from pathlib import Path

log_path = Path(__file__).parent / "logs"
makedirs(log_path, exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console_formatter = ColoredFormatter(
    "%(asctime)s - %(log_color)s%(levelname)s%(reset)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    reset=True,
)

file_formatter = logging.Formatter(
    "%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console_handler = logging.StreamHandler(stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(console_formatter)

file_handler = TimedRotatingFileHandler(
    log_path / "asmr.log",
    when="D",
    backupCount=1,
    encoding="utf8",
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(file_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)
