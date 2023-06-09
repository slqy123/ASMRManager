import os.path
from pathlib import Path

from config import config
from logger import logger

from typing import Optional, Iterable, List, Tuple, Literal, TYPE_CHECKING

import click
import functools

if TYPE_CHECKING:
    from spider import ASMRSpiderManager
    from database.manage import DataBaseManager


def create_database():
    from database.manage import DataBaseManager
    return DataBaseManager(tag_filter=config.tag_filter or tuple())


def create_spider_and_database(
        dl_func: Literal['force', 'folder_not_exists', 'db_not_exists'] = 'db_not_exists'
) -> Tuple['ASMRSpiderManager', 'DataBaseManager']:
    from spider import ASMRSpider, ASMRSpiderManager
    from database.manage import DataBaseManager
    db = create_database()

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
        func = lambda rj_id: True
    return ASMRSpiderManager(spider, func), db  # type: ignore


def create_fm():
    from file_manager.manager import FileManager
    fm = FileManager(storage_path=config.storage_path,
                     download_path=config.save_path,
                     view_path=config.view_path)
    return fm


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
    @click.option('-p', '--page', type=int, default=1, help='page of the search result', show_default=True)
    @click.option('--subtitle/--no-subtitle', '-s/-ns', is_flag=True, default=False,
                  help='if the ASMR has subtitle(中文字幕)', show_default=True)
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
    ], case_sensitive=False), default='release', help='ordering of the search result', show_default=True)
    @click.option('--asc/--desc', default=False, help='ascending or descending')
    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options


def get_prev_rj():
    path = Path(__file__).parent.parent / '.prev_rj'
    if not os.path.exists(path):
        return ''
    with open(path, 'r', encoding='utf8') as f:
        rj = f.read()
    logger.info(f'previous RJ id is {rj}')
    return rj


def save_rj(rj: str):
    path = Path(__file__).parent.parent / '.prev_rj'
    with open(path, 'w', encoding='utf8') as f:
        f.write(rj)


def rj_argument(f):
    """parse the rj_id: int, if not given it will use the previous rj_id"""

    @click.argument('rj_id', type=str, default='__default__')
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        rj: str = kwargs['rj_id']
        if kwargs['rj_id'] == '__default__':
            rj = get_prev_rj()
        if rj == '':
            logger.error('No previous RJ id available, please first run a command with Rj id')
            exit(-1)

        rj_id = rj2id(rj)
        if rj_id is None:
            logger.error(f'Invalid input RJ ID{rj}')
            exit(-1)
        save_rj(rj)
        kwargs['rj_id'] = rj_id

        f(*args, **kwargs)

    return wrapper

SEPARATOR = ':'
def interval_preprocess_cb(ctx: click.Context, opt: click.Option, val: str):
    """input must be numeric or None, and it returns a float/int/None value tuple"""
    vals = val.split(SEPARATOR)
    assert len(vals) == 2

    def _check(x):
        if x == '':
            return None
        xf = float(x)
        if xf.is_integer():
            return int(xf)
        return xf


    return tuple(
        map(
            _check,
            vals
        )
    )
