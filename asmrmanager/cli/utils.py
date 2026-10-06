import sys
from pathlib import Path
from typing import Literal

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
@click.option("--root", "roots", type=click.Path(exists=True, file_okay=False, path_type=Path), multiple=True,
              help="Legacy files to import; defaults to download and storage paths.")
def migrate(roots: tuple[Path, ...]):
    """Back up and migrate the database, importing legacy metadata files."""
    from sqlalchemy.exc import SQLAlchemyError

    from asmrmanager.cli.core import create_database
    from asmrmanager.database.engine import get_engine
    from asmrmanager.database.migrate import migrate_database

    try:
        result = migrate_database(
            get_engine(), list(roots) if roots else [fm.download_path, fm.storage_path],
            playlist_cache=fm.CACHE_PATH / "playlist.cache",
        )
    except (OSError, ValueError, SQLAlchemyError) as exc:
        raise click.ClickException(str(exc)) from exc
    create_database.cache_clear()
    if result.backup is not None:
        click.echo(f"Database backup: {result.backup}")
    click.echo(
        f"Imported {result.details} work details, {result.recoveries} recovery sets, "
        f"{result.playlists} playlists; skipped {result.skipped}. Legacy files were kept."
    )
    if result.errors:
        for error in result.errors:
            click.echo(error, err=True)
        raise click.ClickException(f"{len(result.errors)} legacy imports failed.")


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
        logger.error("The source was not found.")
        sys.exit(-1)
    if mode == "lrc":
        for vtt_path in path.rglob("*.vtt"):
            convert_vtt2lrc(vtt_path)
            assert (
                vtt_path.with_suffix(".lrc").exists()
                or vtt_path.with_suffix("").with_suffix(".lrc").exists()
            )
            logger.info("Converted %s to LRC.", vtt_path)
            vtt_path.unlink()
    else:
        from asmrmanager.common.fileconverter import AudioConverter

        src_paths = list(
            filter(
                lambda p: (
                    not p.is_dir()
                    and p.suffix.lower() in [".flac", ".wav", ".m4a"]
                    and p.suffix.lower() != f".{mode}"
                ),
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
    output: Path | None,
    force: bool = False,
):
    """generate LRC subtitles for audio files using the Whisper model"""
    from asmrmanager.filemanager.utils import folder_chooser

    rj_path = fm.get_path(source_id)
    if rj_path is None:
        logger.error(f"RJ ID {source_id} was not found.")
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
            f"No music files with supported extensions ({MUSIC_SUFFIXES}) were found. "
            "Check the local files and try again."
        )
        sys.exit(-1)

    assert path.is_dir()

    audio_paths: list[Path] = []
    for file in path.iterdir():
        if file.is_dir():
            continue

        if file.suffix not in MUSIC_SUFFIXES:
            continue

        audio_paths.append(file)

    if not audio_paths:
        logger.error("No audio files were found in the specified directory.")
        return

    audio_paths.sort()
    try:
        for audio_path in audio_paths:
            logger.info(f"Generating an LRC file for {audio_path.name}.")
            generate_subtitle(audio_path, output, force)
    except KeyboardInterrupt:
        logger.error("Subtitle generation was interrupted by the user.")
        return


@click.command("fetch-all-covers")
def fetch_all_covers():
    """
    fetch all covers for works in storage path
    """
    from asmrmanager.cli.core import create_database, create_general_api
    from asmrmanager.database.database import ASMR

    manager = create_general_api()
    db = create_database()
    tasks = []

    async def download_cover(remote_id: RemoteSourceID, save_path: Path):
        image_data: bytes = await manager.api.get_cover(remote_id)
        with open(save_path / "cover.jpg", "wb") as f:  # noqa: ASYNC230
            f.write(image_data)
        logger.info("Saved the cover to %s.", save_path)

    for local_id, remote_id in db.query(ASMR.id, ASMR.remote_id).all():
        # print(local_id, remote_id)
        if fm.get_path(local_id, "cover.jpg") is None:
            save_path = fm.storage_path / id2source_name(local_id)
            if not save_path.exists():
                logger.debug(
                    "%s was not found in storage.", id2source_name(local_id)
                )
                continue
            tasks.append(download_cover(remote_id, save_path))

    manager.run(*tasks)


utils.add_command(migrate)
utils.add_command(convert)
utils.add_command(subtitle)
utils.add_command(fetch_all_covers)
