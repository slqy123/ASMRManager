from pathlib import Path
from typing import List, Literal, Optional

import click

from asmrmanager.cli.core import fm, rj_argument
from asmrmanager.common import MUSIC_SUFFIXES
from asmrmanager.common.fileconverter import convert_vtt2lrc
from asmrmanager.common.rj_parse import id2source_name
from asmrmanager.common.subtitle import generate_subtitle
from asmrmanager.common.types import LocalSourceID, RemoteSourceID
from asmrmanager.logger import logger


@click.group()
def utils():
    """
    Some useful utilities
    """


@click.command()
def migrate():
    "migrate the database to the latest version(2.0.0+)"
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
@click.argument("mode", type=click.Choice(["lrc", "mp3", "flac", "m4a"]))
@click.option(
    "--dst",
    type=click.Choice(["download", "storage"]),
    default="storage",
    help="path to apply convert",
)
@rj_argument("local")
def convert(
    source_id: LocalSourceID,
    mode: Literal["lrc", "mp3", "flac", "m4a"],
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
            assert (
                vtt_path.with_suffix(".lrc").exists()
                or vtt_path.with_suffix("").with_suffix(".lrc").exists()
            )
            logger.info("Converted %s to LRC", vtt_path)
            vtt_path.unlink()
    else:
        from asmrmanager.common.fileconverter import AudioConverter

        src_paths = list(
            filter(
                lambda p: not p.is_dir()
                and p.suffix.lower() in [".flac", ".wav", ".m4a"]
                and p.suffix.lower() != f".{mode}",
                path.rglob("*.*"),
            )
        )

        with AudioConverter(f"utils convert to {mode}") as converter:
            converter.convert(*src_paths, dst=mode)
        for src_path in src_paths:
            if src_path.suffix.lower() == f".{mode}":
                continue
            if src_path.with_suffix(f".{mode}").exists():
                logger.info("Removing old file: %s", src_path)
                src_path.unlink()


@click.command()
@rj_argument("local")
@click.option(
    "--force", "-f", is_flag=True, help="Overwrite existing LRC files"
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file path (defaults to a .lrc file with the same name as the audio file)",
)
def subtitle(
    source_id: LocalSourceID,
    output: Optional[Path],
    force: bool = False,
):
    """generate LRC subtitles for audio files using the Whisper model"""
    from asmrmanager.filemanager.utils import folder_chooser

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

    assert path.is_dir()

    audio_paths: List[Path] = []
    for file in path.iterdir():
        if file.is_dir():
            continue

        if file.suffix not in MUSIC_SUFFIXES:
            continue

        audio_paths.append(file)

    if not audio_paths:
        logger.error("No audio files found in the specified directory.")
        return

    audio_paths.sort()
    try:
        for audio_path in audio_paths:
            logger.info(f"Generating LRC file for {audio_path.name}")
            generate_subtitle(audio_path, output, force)
    except KeyboardInterrupt:
        logger.error("Subtitle generation interrupted by user.")
        return


@click.command("fetch-all-covers")
def fetch_all_covers():
    """
    fetch all covers for works in storage path
    """
    from asmrmanager.cli.core import create_downloader_and_database
    from asmrmanager.database.database import ASMR
    from asmrmanager.spider.utils.concurrency import concurrent_rate_limit

    downloader, db = create_downloader_and_database()
    tasks = []

    @concurrent_rate_limit(4, 8)
    async def download_cover(remote_id: RemoteSourceID, save_path: Path):
        image_data: bytes = await downloader.api.get_cover(remote_id)
        with open(save_path / "cover.jpg", "wb") as f:
            f.write(image_data)
        logger.info("Successfully write cover to %s", save_path)

    for local_id, remote_id in db.query(ASMR.id, ASMR.remote_id).all():
        # print(local_id, remote_id)
        if fm.get_path(local_id, "cover.jpg") is None:
            save_path = fm.storage_path / id2source_name(local_id)
            if not save_path.exists():
                logger.debug(
                    "%s not found in storage", id2source_name(local_id)
                )
                continue
            tasks.append(download_cover(remote_id, save_path))

    downloader.run(*tasks)


utils.add_command(migrate)
utils.add_command(convert)
utils.add_command(subtitle)
utils.add_command(fetch_all_covers)
