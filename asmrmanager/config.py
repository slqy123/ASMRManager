from dataclasses import dataclass
import os
from typing import Dict, List, Literal

import toml

from asmrmanager import CONFIG_PATH
from asmrmanager.logger import logger


@dataclass
class Config:
    username: str
    password: str
    proxy: str | None
    api_channel: str | None
    api_max_concurrent_requests: int
    api_max_requests_per_second: int
    download_path: str
    storage_path: str
    view_path: str
    tag_strategy: Literal["common_only", "accept_all", "except_rejected"] | str
    tag_filter: List[str]
    editor: str
    filename_filters: List["Filter"]
    download_method: Literal["aria2", "idm"]
    idm_install_path: str | None
    aria2_config: "Aria2Config"
    subtitle_config: "SubtitleConfig"
    playlist_aliases: Dict[str, str]
    player: Literal["mpd", "pygame"]
    mpd_config: "MPDConfig"
    before_store: str = ""


@dataclass
class Filter:
    regex: str = ""  # 正则表达式

    # 该规则是包含还是排除，注意只有满足所有的include规则且不满足所有的exclude规则才会被下载
    type: Literal["include", "exclude"] = "exclude"

    range: Literal["file", "directory", "all"] = "all"  # 该规则针对的文件类型
    excat_match: bool = False  # 是否应精确匹配(从头到尾严格匹配)
    ignore_case: bool = True  # 是否忽略大小写
    disable_when_nothing_to_download: bool = False


@dataclass
class Aria2Config:
    host: str = "http://localhost"
    port: int = 6800
    secret: str = ""


@dataclass
class MPDConfig:
    bin: str = "mpd"
    host: str = "localhost"
    port: int = 6600
    music_directory: str | None = None


@dataclass
class SubtitleConfig:
    device: str = "auto"
    model_size: str = "base"
    language: str = "ja"


_config = toml.load(CONFIG_PATH / "config.toml")

_filename_filters: list = _config.get("filename_filters", [])
filename_filters = list(
    map(
        lambda x: Filter(**x) if isinstance(x, dict) else Filter(x),
        _filename_filters,
    )
)
# _aria2_config: dict = _config.get("aria2_config", {})
# aria2_config = Aria2Config(**_aria2_config)

# playlist_aliases: dict = _config.get("playlist_aliases", {})

# _mpd_config: dict = _config.get("mpd_config", {})
# mpd_config = MPDConfig(**_mpd_config)
# mpd_config.bin = os.path.expanduser(mpd_config.bin)
# if isinstance(mpd_config.conf_path, str):
#     mpd_config.conf_path = os.path.expanduser(mpd_config.conf_path)

config = Config(
    username=_config["username"],
    password=_config["password"],
    proxy=_config.get("proxy", None),
    api_channel=_config.get("api_channel", None),
    api_max_concurrent_requests=_config.get("api_max_concurrent_requests", 4),
    api_max_requests_per_second=_config.get("api_max_requests_per_second", 4),
    download_path=_config["download_path"],
    storage_path=_config["storage_path"],
    view_path=_config["view_path"],
    tag_strategy=_config.get("tag_strategy", "common_only"),
    tag_filter=_config["tag_filter"],
    editor=_config["editor"],
    filename_filters=filename_filters,
    download_method=_config["download_method"],
    idm_install_path=_config.get("idm_install_path", None),
    aria2_config=Aria2Config(**_config.get("aria2_config", {})),
    playlist_aliases=_config.get("playlist_aliases", {}),
    player=_config.get("player", "pygame"),
    mpd_config=MPDConfig(**_config.get("mpd_config", {})),
    before_store=_config.get("before_store", ""),
    subtitle_config=SubtitleConfig(**_config.get("subtitle_config", {})),
)

# environment variable override
if env_concurrency_limit := os.getenv("ASMR_CONCURRENCY_LIMIT"):
    creq, crps = eval(env_concurrency_limit)
    assert isinstance(creq, int) and isinstance(crps, int)
    config.api_max_concurrent_requests = creq
    config.api_max_requests_per_second = crps

logger.debug(f"Config loaded: {config}")
