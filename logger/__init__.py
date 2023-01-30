from sys import stdout

from loguru import logger
from os import makedirs
from pathlib import Path

log_path = Path(__file__).parent / 'logs'
makedirs(log_path, exist_ok=True)
logger.remove()
format_ = "<g>{time:MM-DD HH:mm:ss}</g> [<lvl>{level}</lvl>] | {message}"
logger.add(stdout, format=format_)
logger.add(
    log_path / 'asmr.log',
    format=format_,
    rotation="1 day",
    encoding='utf-8'
)
