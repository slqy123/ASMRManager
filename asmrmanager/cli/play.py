import click

from asmrmanager.cli.core import fm, rj_argument
from asmrmanager.common.types import LocalSourceID
from asmrmanager.logger import logger


@click.command()
@click.pass_context
@rj_argument("local")
def play(ctx: click.Context, source_id: LocalSourceID):
    """play asmr with a simple TUI"""
    from asmrmanager.filemanager.utils import folder_chooser
    from asmrmanager.lrcplayer import lrc_play
    from asmrmanager.common import MUSIC_SUFFIXES

    rj_path = fm.get_path(source_id)
    if rj_path is None:
        logger.error(f"RJ id {source_id} not found!")
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
            f"No music files{MUSIC_SUFFIXES} found, please check your local"
            " file."
        )
        exit(-1)

    ctx.invoke(lrc_play, path=path)
