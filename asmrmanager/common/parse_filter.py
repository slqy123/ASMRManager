import re
from typing import Literal

from asmrmanager.config import config


def name_should_download(
    name: str, type_: Literal["directory", "file"], disable: bool = False
):
    for filter_ in config.filename_filters:
        if disable and filter_.disable_when_nothing_to_download:
            continue
        range_check = filter_.range == "all" or filter_.range == type_
        if not range_check:
            continue

        flag = re.IGNORECASE if filter_.ignore_case else 0

        match_method = re.fullmatch if filter_.excat_match else re.search

        regex_match = bool(match_method(filter_.regex, name, flag))

        if regex_match ^ (filter_.type == "include"):
            return False

    return True


if __name__ == "__main__":
    print(name_should_download("効果音なしver", type_="directory"))
