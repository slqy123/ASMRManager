import click

from asmrmanager.cli.core import rj_argument
from asmrmanager.common.types import LocalSourceID
from asmrmanager.logger import logger


@click.command()
@rj_argument("local")
@click.option("-c", "--comment", type=str, default=None, show_default=True)
def hold(source_id: LocalSourceID, comment: str | None = None):
    """set the ASMR.hold to true, and add a comment for the reason"""
    logger.info(f"run command hold with rj_id={source_id} comment={comment}")

    from asmrmanager.cli.core import create_database

    db = create_database()
    db.hold_item(source_id, comment)
    db.commit()
