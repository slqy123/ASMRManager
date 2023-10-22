import click
import os

from asmrmanager.common.rj_parse import RJID, id2rj
from asmrmanager.cli.core import rj_argument
from asmrmanager.logger import logger


@click.command()
@rj_argument
def show(rj_id: RJID):
    """Show directory in file explorer"""
    from asmrmanager.cli.core import fm

    match fm.get_location(rj_id):
        case "download":
            path = fm.download_path
        case "storage":
            path = fm.storage_path
        case None:
            logger.error(f"id {rj_id} not exists")
            return
        case _:
            raise NotImplementedError

    os.system(f'explorer.exe "{path / id2rj(rj_id)}"')
