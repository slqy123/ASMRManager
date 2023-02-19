import click
from logger import logger


@click.command()
@click.argument('rj_id', type=str)
@click.option('-c', '--comment', type=str, default=None)
def hold(rj_id: str, comment: int = None):
    logger.info(f'run command hold with rj_id={rj_id} comment={comment}')
    rj_id = int(rj_id[2:]) if rj_id.startswith('RJ') else int(rj_id)

    from asmrcli.core import create_database
    db = create_database()
    db.hold_item(rj_id, comment)
    db.commit()
