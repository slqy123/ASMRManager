from dataclasses import dataclass
from typing import List, Literal


@dataclass
class Config:
    username: str
    password: str
    proxy: str
    download_path: str
    storage_path: str
    view_path: str
    tag_filter: List[str]
    editor: str
    filename_filters: List["Filter"]
    download_method: Literal["aria2", "idm"]
    aria2_config: "Aria2Config"


@dataclass
class Filter:
    regex: str = ""  # 正则表达式

    # 该规则是包含还是排除，注意只有满足所有的include规则且不满足所有的exclude规则才会被下载
    type: Literal["include", "exclude"] = "exclude"

    range: Literal["file", "directory", "all"] = "all"  # 该规则针对的文件类型
    excat_match: bool = False  # 是否应精确匹配(从头到尾严格匹配)
    ignore_case: bool = True  # 是否忽略大小写


@dataclass
class Aria2Config:
    host: str = "http://localhost"
    port: int = 6800
    secret: str = ""


# -----------------------------------------------------
# 以下是配置文件的示例，上方的内容请勿修改
# -----------------------------------------------------


config = Config(
    # 账号
    username="username",
    # 密码
    password="password",
    # 代理
    proxy="http://localhost:7890",
    # 下载文件的临时存放位置
    download_path="/path/to/some/place",
    # 文件最终存储位置
    # 使用review后，如果文件在download_path，将自动移至storage_path
    storage_path="/path/to/some/place",
    # 使用asmr view 的时候会在这个位置创建一个软链接或压缩文件，方便查找。
    # 如不使用 view 方法可以设为空
    view_path="/path/to/some/place",
    # 过滤掉那些你不喜欢的标签
    tag_filter=["tagname1", "tagname2"],
    # 编辑sql用的默认编辑器, 如果需使用powershell脚本例如lvim，
    # 此处可填入 'pwsh -nop -f /path/to/lvim.ps1'
    editor="code --wait",
    # 文件和文件夹的过滤规则
    filename_filters=[
        # 过滤所有的SE(不完全)
        Filter(r"(効果音|SE|ＳＥ|BGM|音效)([な無无×][し]?|cut|切除|カット)"),
        Filter(r"([無无×]|不含|NO[ _]?)(効果音|SE|ＳＥ|BGM|音效)"),
        Filter(r"(声|ボイス|SE)のみ"),
        # 过滤所有的wav
        Filter(r".*\.wav$", range="file"),
        # 过滤包含 "反転" 的wav文件
        Filter(r"反転.*\.wav$", range="file"),
    ],
    # 下载所用的工具
    download_method="idm",
    # 如使用aria2请配置此项，否则请忽略
    aria2_config=Aria2Config(),
)
