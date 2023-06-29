import click
from asmrcli.core import create_database, rj2id, rj_argument, create_spider_and_database
from pprint import pprint
from logger import logger

def info_from_web(rj_id: int):
    raise NotImplementedError
    # spider, db = create_spider_and_database()
    # spider.run(spider.get([rj_id]))
    # db.commit()

@click.command()
@click.option('--rand', '-r', is_flag=True, default=False, show_default=True, help='get a random info in the database')
@rj_argument
def info(rj_id: int, rand: bool):
    """show info of the ASMR by id"""
    db = create_database()

    v_info = db.func.get_info(rj_id, rand=rand)
    if v_info is None:
        logger.info(f'RJ{rj_id} not exists, try getting from web')
        info_from_web(rj_id)
        return

    res: dict = v_info.__dict__.copy()
    res.pop('_sa_instance_state')
    pprint(res)
    print(' tags:', v_info.tags)
    print(' CVs:', v_info.vas)
