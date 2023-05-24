import click
from logger import logger
from asmrcli.core import rj_argument


@click.command()
@rj_argument
@click.option('-s', '--star', type=int)
@click.option('-c', '--comment', type=str)
def review(rj_id: int, star: int, comment: str):
    logger.info(f'run command review with rj_id={rj_id}, star={star} comment={comment}')

    from asmrcli.core import create_database
    db = create_database()
    db.update_review(rj_id, star, comment)
    db.commit()




