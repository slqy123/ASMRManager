from typing import Literal

import click

from asmrmanager.cli.core import rj_argument
from asmrmanager.common.fileconverter import convert_vtt2lrc
from asmrmanager.common.types import LocalSourceID
from asmrmanager.logger import logger


@click.group()
def utils():
    """
    Some useful utilities
    """


@click.command()
def migrate():
    "mirate the database to the latest version(3.0.0+)"
    from sqlalchemy.sql import text

    from asmrmanager.cli.core import create_database

    db = create_database(skip_check=True)
    if db.check_db_updated():
        logger.error("Database already updated")
        exit(-1)
    db.session.execute(text("ALTER TABLE asmr ADD COLUMN remote_id integer;"))
    db.session.execute(text("UPDATE asmr SET remote_id = id;"))
    db.session.commit()
    logger.info("Database updated successfully")


@click.command()
@click.argument("mode", type=click.Choice(["lrc", "mp3", "flac"]))
@click.option(
    "--dst",
    type=click.Choice(["download", "storage"]),
    default="storage",
    help="path to apply convert",
)
@rj_argument("local")
def convert(
    source_id: LocalSourceID,
    mode: Literal["lrc", "mp3", "flac"],
    dst: Literal["download", "storage"],
):
    """convert file format and replace the existing file"""
    from asmrmanager.filemanager.manager import FileManager

    fm = FileManager.get_fm()

    path = fm.get_path(source_id, prefer=dst)
    if path is None:
        logger.error("Source not found")
        exit(-1)
    if mode == "lrc":
        for vtt_path in path.rglob("*.vtt"):
            convert_vtt2lrc(vtt_path)
            assert vtt_path.with_suffix(".lrc").exists()
            vtt_path.unlink()
    elif mode in ("mp3", "flac"):
        from asmrmanager.common.fileconverter import convert_audio_format

        for wav_path in path.rglob("*.wav"):
            convert_audio_format(wav_path, mode)
            assert wav_path.with_suffix(f".{mode}").exists()
            wav_path.unlink()


utils.add_command(migrate)
utils.add_command(convert)
