import click
from logger import logger
from asmrcli.core import rj_argument


@click.command()
@rj_argument
@click.option("-c", "--comment", type=str, default=None, show_default=True)
def hold(rj_id: int, comment: str | None = None):
    """set the ASMR.hold to true, and add a comment for the reason"""
    logger.info(f"run command hold with rj_id={rj_id} comment={comment}")

    from asmrcli.core import create_database

    db = create_database()
    db.hold_item(rj_id, comment)
    db.commit()
