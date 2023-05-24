from dataclasses import dataclass
from typing import Sequence


@dataclass
class Config:
    username: str = 'username'
    password: str = 'password'
    proxy: str = 'http://localhost:7890'
    save_path: str = '/path/to/some/place'
    storage_path: str = '/path/to/some/place'
    view_path: str = '/path/to/some/place'
    tag_filter: Sequence[str] = ('tagname1', 'tagname2')


config = Config()
