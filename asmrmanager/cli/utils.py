import os
import shlex
import subprocess
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
              help="Legacy roots for existing database works; defaults to download and storage paths.")
def migrate(roots: tuple[Path, ...]):
    """Back up and migrate the database, importing metadata for existing works."""
    from sqlalchemy.exc import SQLAlchemyError

    from asmrmanager.cli.core import create_database
    from asmrmanager.database.database import ASMR
    from asmrmanager.database.engine import get_engine
    from asmrmanager.database.manage import DataBaseManager
    from asmrmanager.database.migrate import migrate_database

    migration_roots = list(dict.fromkeys(
        path.resolve() for path in (roots or (fm.download_path, fm.storage_path))
    ))
    engine = get_engine()
    try:
        result = migrate_database(engine, migration_roots)
    except (OSError, ValueError, SQLAlchemyError) as exc:
        raise click.ClickException(str(exc)) from exc
    create_database.cache_clear()
    if result.backup is not None:
        click.echo(f"Database backup: {result.backup}")
    click.echo(
        f"Imported {result.details} work details, {result.recoveries} recovery sets. "
        "Legacy files were kept."
    )
    db = DataBaseManager(engine)
    try:
        missing = db.session.query(ASMR).filter(ASMR.details.is_(None)).count()
    finally:
        db.session.close()
    click.echo(f"Works still missing details: {missing}. Run asmr utils migrate-update to fetch them from the API.")
    cleanup_roots = " ".join(
        "--root " + ("'" + str(root).replace("'", "''") + "'" if os.name == "nt" else shlex.quote(str(root)))
        for root in migration_roots
    )
    click.echo(f"After verifying the migrated data, run: asmr utils migrate-cleanup {cleanup_roots}")
    if result.errors:
        click.echo("Some imports failed. Keep legacy JSON and .recover files; fix the errors and rerun migration.")
        for error in result.errors:
            click.echo(error, err=True)
        raise click.ClickException(f"{len(result.errors)} legacy imports failed.")
    click.echo("Migration complete. Legacy files were kept.")


@click.command("migrate-playlists")
def migrate_playlists():
    """Import owned cloud playlists and their members without overwriting local lists."""
    from sqlalchemy.exc import SQLAlchemyError

    from asmrmanager.cli.core import create_database, create_sync_api
    from asmrmanager.cli.sync import apply_difference, differences
    from asmrmanager.config import config
    from asmrmanager.database.database import ASMR
    from asmrmanager.sync import SyncError

    if not config.sync.playlist:
        raise click.ClickException("Enable sync.playlist before migrating playlists; no cloud request was made.")
    db = create_database()
    try:
        manager = create_sync_api()
        linked = {
            item.remote_id: item for item in db.list_playlists()
            if item.remote_id is not None
        }
        for item in linked.values():
            manager.binding(item)
        snapshot = manager.run(manager.snapshot(
            False, True, {work.id for work in db.session.query(ASMR)},
        ))[0]
        changes, _ = differences(db, snapshot, (), True)
        imported = 0
        skipped = len(linked.keys() & snapshot.playlists.keys())
        for change in changes:
            if change.key not in linked and change.kind == "playlist":
                apply_difference(db, snapshot, manager, change)
                imported += 1
        db.commit()
    except (SyncError, SQLAlchemyError, ValueError, KeyError, TypeError, AssertionError) as exc:
        db.session.rollback()
        raise click.ClickException(f"Playlist migration failed; local changes were rolled back. {exc}") from exc
    click.echo(f"Imported {imported} playlists; skipped {skipped} already-bound playlists.")


@click.command("migrate-cleanup")
@click.option("--root", "roots", type=click.Path(exists=True, file_okay=False, path_type=Path), multiple=True,
              help="Legacy roots to clean; defaults to download and storage paths.")
def migrate_cleanup(roots: tuple[Path, ...]):
    """Confirm and delete shallow legacy metadata files."""
    migration_roots = list(dict.fromkeys(
        path.resolve() for path in (roots or (fm.download_path, fm.storage_path))
    ))
    click.echo(
        "Verify work details and recovery records, "
        "then back up the current data.db before deleting legacy files. "
        "Review the command before confirming; it also matches works absent from the database "
        "that were not imported. Keep those files if needed. "
        "Do not delete other JSON files, audio files, or database backups."
    )
    bash_roots = " ".join(shlex.quote(str(root)) for root in migration_roots)
    powershell_roots = ", ".join(
        "'" + str(root).replace("'", "''") + "'" for root in migration_roots
    )
    find_command = (
        f"find {bash_roots} -regextype posix-extended -mindepth 2 -maxdepth 2 "
        r"-type f \( -name .recover -o -regex '.*/(RJ|VJ|BJ)[0-9]+\.json' \)"
    )
    bash_command = f"{find_command} -delete -print"
    powershell_command = f"""Get-ChildItem -LiteralPath @({powershell_roots}) -Directory -Force -ErrorAction Stop |
    Where-Object {{ -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) }} |
    ForEach-Object {{ Get-ChildItem -LiteralPath $_.FullName -File -Force -ErrorAction Stop }} |
    Where-Object {{
        -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -and
        ($_.Name -ceq '.recover' -or $_.Name -cmatch '^(RJ|VJ|BJ)[0-9]+\\.json$')
    }} | ForEach-Object {{ Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop }}
"""
    command = powershell_command if os.name == "nt" else bash_command
    click.echo(f"Command to execute:\n{command}")
    click.confirm("Delete these legacy files?", default=False, abort=True)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", command] if os.name == "nt"
            else ["bash", "-c", command],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise click.ClickException(str(exc)) from exc


@click.command("migrate-update")
def migrate_update():
    """Fetch missing work details without changing recovery records."""
    from sqlalchemy.exc import SQLAlchemyError

    from asmrmanager.cli.core import create_database, create_general_api
    from asmrmanager.common.rj_parse import source2id
    from asmrmanager.database.database import ASMR
    from asmrmanager.spider.asmrapi import APIError

    db = create_database()
    works = db.session.query(ASMR.id, ASMR.remote_id).filter(ASMR.details.is_(None)).all()
    if not works:
        click.echo("No works are missing details.")
        return
    manager = create_general_api()
    errors = []

    async def update_missing():
        for source_id, remote_id in works:
            source_name = id2source_name(source_id)
            try:
                if remote_id is None:
                    search = await manager.api.get_search_result(source_name, {})
                    matches = [item for item in search["works"] if item.get("source_id") == source_name]
                    if len(matches) != 1:
                        raise ValueError("Could not uniquely resolve the remote work.")
                    remote_id = matches[0]["id"]
                info = await manager.api.get_voice_info(remote_id, refresh=True)
                if info is None or source2id(info["source_id"]) != source_id:
                    raise ValueError("Missing details or mismatched work ID.")
                db.add_info(info, check=False, tag_strategy="accept_all")
                db.session.commit()
                click.echo(f"Updated {source_name}.")
            except (OSError, ValueError, TypeError, KeyError, AssertionError, SQLAlchemyError, APIError) as exc:
                db.session.rollback()
                errors.append(f"{source_name}: {type(exc).__name__}: {exc}")

    try:
        manager.run(update_missing())
    finally:
        db.session.rollback()
    if errors:
        for error in errors:
            click.echo(error, err=True)
        raise click.ClickException(f"{len(errors)} works failed; rerun migrate-update to retry.")
    click.echo("Missing work details updated. Recovery records were kept.")


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
utils.add_command(migrate_update)
utils.add_command(migrate_playlists)
utils.add_command(migrate_cleanup)
utils.add_command(convert)
utils.add_command(subtitle)
utils.add_command(fetch_all_covers)
