from dataclasses import dataclass
from typing import Sequence


@dataclass
class Config:
    username: str = 'username'  # 账号
    password: str = 'password'  # 密码
    proxy: str = 'http://localhost:7890'  # 代理
    save_path: str = '/path/to/some/place'  # 下载文件的存储位置
    storage_path: str = '/path/to/some/place'  # 使用review后，如果文件在save_path，将自动移至storage_path
    view_path: str = '/path/to/some/place'  # (可选)使用asmr view 的时候会在这个位置创建一个软链接，方便找。
    tag_filter: Sequence[str] = ('tagname1', 'tagname2')  # 过滤掉那些你不喜欢的标签
    editor: str = 'code'  # 编辑sql用的默认编辑器


config = Config()
