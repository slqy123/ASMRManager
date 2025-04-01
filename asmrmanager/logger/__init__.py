import logging
from logging.handlers import TimedRotatingFileHandler
from os import makedirs, environ
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback

install_rich_traceback()

from asmrmanager.filemanager.appdirs_ import LOG_PATH

LOG_LEVEL = logging.INFO
if environ.get("ASMR_DEBUG"):
    LOG_LEVEL = logging.DEBUG
if environ.get("ASMR_TEST"):
    LOG_LEVEL = logging.WARNING
if environ.get("_ASMR_COMPLETE") is not None:
    LOG_LEVEL = logging.CRITICAL

log_path = LOG_PATH
makedirs(log_path, exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

console_handler = RichHandler(
    LOG_LEVEL, Console(stderr=True), rich_tracebacks=True, markup=True
)

file_formatter = logging.Formatter(
    "%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
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
