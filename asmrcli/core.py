from spider import ASMRSpider, ASMRSpiderManager
from database.manage import DataBaseManager
from config import config
from typing import Optional, Iterable, List, Tuple


def create_database():
    return DataBaseManager()


def create_spider_and_database() -> Tuple[ASMRSpiderManager, DataBaseManager]:
    db = DataBaseManager()

    spider = ASMRSpider(name=config.username,
                        password=config.password,
                        proxy=config.proxy,
                        save_path=config.save_path,
                        download_callback=db.add_info)

    return ASMRSpiderManager(spider, lambda rj_id: not db.check_exists(rj_id)), db
    # return ASMRSpiderManager(spider, lambda rj_id: True), db


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
