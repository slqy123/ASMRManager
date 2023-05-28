import click
from asmrcli.core import create_database, rj2id, rj_argument
from pprint import pprint
from logger import logger


@click.command()
@rj_argument
def info(rj_id: int):
    """show info of the ASMR by id"""
    db = create_database()

    v_info = db.func.get_info(rj_id)
    if v_info is None:
        logger.error(f'RJ{rj_id} not exists')
        return

    res: dict = v_info.__dict__.copy()
    res.pop('_sa_instance_state')
    pprint(res)
    print(' tags:', v_info.tags)
    print(' CVs:', v_info.vas)
