import click

from asmrmanager.cli.core import create_database, fm, rj_argument
from asmrmanager.common.rj_parse import RJID, id2rj
from asmrmanager.config import config
from asmrmanager.filemanager.utils import folder_chooser
from asmrmanager.logger import logger


@click.command()
@click.pass_context
@rj_argument
def play(ctx: click.Context, rj_id: RJID):
    """play an asmr in the terminal"""
    from asmrmanager.lrcplayer import MUSIC_SUFFIXES, lrc_play

    rj_path = fm.get_path(rj_id)
    if rj_path is None:
        logger.error(f"RJ id {rj_id} not found!")
        return

    path = folder_chooser(
        rj_path,
        lambda _, count: bool(set(count.keys()).intersection(MUSIC_SUFFIXES)),
    )

    ctx.invoke(lrc_play, path=path)
