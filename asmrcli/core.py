import os.path

from spider import ASMRSpider, ASMRSpiderManager
from database.manage import DataBaseManager
from config import config
from typing import Optional, Iterable, List, Tuple, Literal

import click
import functools
def create_database():
    return DataBaseManager()


def create_spider_and_database(
        dl_func: Literal['force', 'folder_not_exists', 'db_not_exists'] = 'db_not_exists'
) -> Tuple[ASMRSpiderManager, DataBaseManager]:
    db = DataBaseManager()

    spider = ASMRSpider(name=config.username,
                        password=config.password,
                        proxy=config.proxy,
                        save_path=config.save_path,
                        download_callback=db.add_info)

    if dl_func == 'force':
        func = lambda rj_id: True
    elif dl_func == 'folder_not_exists':
        func = lambda rj_id: not os.path.exists(os.path.join(config.save_path, id2rj(rj_id)))
    elif dl_func == 'db_not_exists':
        func = lambda rj_id: not db.check_exists(rj_id)
    else:
        func = lambda: True
    return ASMRSpiderManager(spider, func), db


# 15 25
def rj2id(rj_id: str) -> Optional[int]:
    try:
        if rj_id.startswith('RJ'):
            return int(rj_id[2:])
        else:
            return int(rj_id)
    except ValueError:
        return None


def rjs2ids(rjs: Iterable[str]) -> List[int]:
    ids = []
    for rj_id in rjs:
        if id_ := rj2id(rj_id):
            ids.append(id_)
    return ids


def id2rj(rj_id: int) -> str:
    return f'RJ{str(rj_id).zfill(6)}'

def browse_param_options(f):
    @click.option('-p', '--page', type=int, default=1)
    @click.option('-s', '--subtitle', is_flag=True, default=False)
    @click.option('-o', '--order', type=click.Choice([
        "create_date",
        "rating",
        "release",
        "dl_count",
        "price",
        "rate_average_2dp",
        "review_count",
        "id",
        "nsfw",
        "random"
    ], case_sensitive=False), default='release')
    @click.option('--asc/--desc', default=False)
    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options