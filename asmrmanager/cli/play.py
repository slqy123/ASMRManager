import click

from asmrmanager.cli.core import create_database, fm, rj_argument
from asmrmanager.common.rj_parse import RJID, id2rj
from asmrmanager.config import config
from asmrmanager.logger import logger


@click.command()
@click.pass_context
@rj_argument
def play(ctx: click.Context, rj_id: RJID):
    from asmrmanager.filemanager.utils import folder_chooser

    """play an asmr in the terminal"""
    from asmrmanager.lrcplayer import MUSIC_SUFFIXES, lrc_play

    rj_path = fm.get_path(rj_id)
    if rj_path is None:
        logger.error(f"RJ id {rj_id} not found!")
        return

    try:
        path = folder_chooser(
            rj_path,
            lambda _, count: bool(
                set(count.keys()).intersection(MUSIC_SUFFIXES)
            ),
        )
    except ValueError:
        logger.error(
            f"No music files{MUSIC_SUFFIXES} found, please check your local file."
        )
        exit(-1)

    ctx.invoke(lrc_play, path=path)
