from dataclasses import dataclass
from typing import Dict, List, Literal

import toml

from asmrmanager import CONFIG_PATH


@dataclass
class Config:
    username: str
    password: str
    proxy: str | None
    api_channel: str | None
    download_path: str
    storage_path: str
    view_path: str
    tag_filter: List[str]
    editor: str
    filename_filters: List["Filter"]
    download_method: Literal["aria2", "idm"]
    aria2_config: "Aria2Config"
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
    download_path=_config["download_path"],
    storage_path=_config["storage_path"],
    view_path=_config["view_path"],
    tag_filter=_config["tag_filter"],
    editor=_config["editor"],
    filename_filters=filename_filters,
    download_method=_config["download_method"],
    aria2_config=Aria2Config(**_config.get("aria2_config", {})),
    playlist_aliases=_config.get("playlist_aliases", {}),
    player=_config.get("player", "pygame"),
    mpd_config=MPDConfig(**_config.get("mpd_config", {})),
    before_store=_config.get("before_store", ""),
)
