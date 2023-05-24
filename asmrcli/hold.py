import click
from logger import logger
from asmrcli.core import rj_argument


@click.command()
@rj_argument
@click.option('-c', '--comment', type=str, default=None)
def hold(rj_id: int, comment: int = None):
    logger.info(f'run command hold with rj_id={rj_id} comment={comment}')

    from asmrcli.core import create_database
    db = create_database()
    db.hold_item(rj_id, comment)
    db.commit()
