import re
from typing import Literal

from asmrmanager.config import config


def name_should_download(
    name: str, type_: Literal["directory", "file"]
) -> int:
    """
    Check if a dir/file name should download.
    This function returns a download_order[int], where:
    download_order == 0: this file/dir should never download
    download_order == 1: this file/dir should download
    download_order >= 2: this file/dir should be download
    by the order of this value, the lower the value
    the higher the priority
    """

    def filter_name(filter_) -> bool:
        """return False if a file is filtered by the filter"""
        if not (filter_.range == "all" or filter_.range == type_):
            return True

        flag = re.IGNORECASE if filter_.ignore_case else 0

        match_method = re.fullmatch if filter_.excat_match else re.search

        regex_match = bool(match_method(filter_.regex, name, flag))

        if regex_match ^ (filter_.type == "include"):
            return False
        return True

    filter_status = []
    for filter_ in config.filename_filters:
        should_download = int(filter_name(filter_))
        if not should_download and filter_.disable_when_nothing_to_download:
            should_download = filter_.disable_order + 1
        if should_download == 0:
            return 0
        filter_status.append(should_download)
    return max(filter_status)


if __name__ == "__main__":
    print(name_should_download("効果音なしver", type_="directory"))
    print(name_should_download("効果音ありver", type_="directory"))
    print(name_should_download("audio.wav", type_="file"))
    print(name_should_download("audio.flac", type_="file"))
