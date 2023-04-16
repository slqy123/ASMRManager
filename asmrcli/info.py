import click
from asmrcli.core import create_database, rj2id
from pprint import pprint
from logger import logger
@click.command()
@click.argument('rj_id', type=str)
def info(rj_id: str):
    db = create_database()

    rj_id_t = rj2id(rj_id)
    if rj_id_t is None:
        click.echo(f'Invalid input RJ ID{rj_id}')
        return

    v_info = db.func.get_info(rj_id_t)
    if v_info is None:
        logger.error(f'RJ{rj_id_t} not exists')
        return

    res: dict = v_info.__dict__.copy()
    res.pop('_sa_instance_state')
    pprint(res)
    print(' tags:', v_info.tags)
    print(' CVs:', v_info.vas)
