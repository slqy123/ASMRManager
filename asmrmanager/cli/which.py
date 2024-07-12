import os

import click

from asmrmanager.cli.core import rj_argument
from asmrmanager.common.types import LocalSourceID
from asmrmanager.logger import logger


@click.command()
@rj_argument("local")
@click.option("--show", is_flag=True, default=False, show_default=True)
def which(source_id: LocalSourceID, show: bool):
    """Get the path from the given source_id"""
    from asmrmanager.cli.core import fm

    path = str(fm.get_path(source_id))

    if not show:
        click.echo(path)
    else:
        import sys

        if sys.platform == "win32":
            os.system(f'explorer.exe "{path}"')
        elif sys.platform.startswith("linux"):
            os.system(f'xdg-open "{path}"')
        else:
            logger.error(
                "option --show is for windows and linux only, if you are using other platform, using"
                " `cd $(asmr which <RJID>)` instead."
            )
            return
