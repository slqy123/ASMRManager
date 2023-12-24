# a simple wrapper for beaupy.select

from typing import List

import beaupy
from beaupy import DefaultKeys
from yakh.key import Keys

from asmrmanager.logger import logger

DefaultKeys.up.append(Keys.CTRL_P)
DefaultKeys.down.append(Keys.CTRL_N)
DefaultKeys.up.append("k")
DefaultKeys.down.append("j")


def select(choices: List[str]) -> int:
    res = beaupy.select(choices, return_index=True)  # type: ignore
    if res is None:
        logger.warning("Selection canceled!")
        exit(-1)
    return res


def select_multiple(choices: List[str]) -> List[int]:
    res = beaupy.select_multiple(choices, return_indices=True)  # type: ignore
    if res is None:
        logger.warning("Selection canceled!")
        exit(-1)
    return res


def confirm(question: str) -> bool:
    res = beaupy.confirm(question)
    if res is None:
        logger.warning("Selection canceled!")
        exit(-1)
    return res
