import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile

import toml
from sqlalchemy import inspect, or_
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from asmrmanager.common.rj_parse import id2source_name, source2id
from asmrmanager.common.types import PRIVACY, LocalSourceID
from asmrmanager.logger import logger

from .database import ASMR, SCHEMA_VERSION, Base, Playlist
from .manage import DataBaseManager


@dataclass
class MigrationResult:
    backup: Path | None = None
    details: int = 0
    recoveries: int = 0
    playlists: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    detail_fallbacks: dict[Path, str] = field(default_factory=dict)


def backup_database(engine: Engine) -> Path | None:
    if engine.dialect.name != "sqlite":
        raise ValueError("Database migration requires SQLite.")
    database = engine.url.database
    if database in (None, "", ":memory:"):
        return None
    path = Path(database)
    if not path.exists():
        return None
    with NamedTemporaryFile(
        prefix=f"{path.stem}.backup-",
        suffix=".db",
        dir=path.parent,
        delete=False,
    ) as file:
        backup = Path(file.name)
    try:
        with (
            closing(sqlite3.connect(path)) as source,
            closing(sqlite3.connect(backup)) as target,
        ):
            source.backup(target)
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
    return backup


def migrate_schema(engine: Engine):
    if engine.dialect.name != "sqlite":
        raise ValueError("Database migration requires SQLite.")
    inspector = inspect(engine)
    columns = (
        {column["name"] for column in inspector.get_columns("asmr")}
        if inspector.has_table("asmr")
        else set()
    )
    with engine.connect() as connection:
        version = connection.exec_driver_sql("PRAGMA user_version").scalar()
        sqlite_version = connection.exec_driver_sql(
            "SELECT sqlite_version()"
        ).scalar()
        if version > SCHEMA_VERSION:
            raise ValueError("Database schema is newer than this application.")
        if "count" in columns and tuple(
            map(int, sqlite_version.split("."))
        ) < (3, 35, 0):
            raise ValueError("Migration requires SQLite 3.35 or newer.")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            if columns:
                additions = {
                    "remote_id": "INTEGER",
                    "progress": "TEXT",
                    "last_review": "DATE",
                    "notes": "TEXT DEFAULT ''",
                    "details": "JSON",
                    "recovery_ready": "BOOLEAN DEFAULT 0",
                }
                for name, type_ in additions.items():
                    if name not in columns:
                        connection.exec_driver_sql(
                            f"ALTER TABLE asmr ADD COLUMN {name} {type_}"
                        )
                if "remote_id" not in columns:
                    connection.exec_driver_sql(
                        "UPDATE asmr SET remote_id = id"
                    )
                if "notes" not in columns:
                    connection.exec_driver_sql(
                        "UPDATE asmr SET notes = COALESCE(comment, ''), comment = ''"
                    )
                if "count" in columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE asmr DROP COLUMN count"
                    )
                connection.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_asmr_remote_id ON asmr(remote_id)"
                )
            Base.metadata.create_all(connection)
            connection.exec_driver_sql(
                f"PRAGMA user_version = {SCHEMA_VERSION}"
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def migrate_database(
    engine: Engine,
    roots: list[Path],
    playlist_cache: Path | None = None,
    remote_service: str | None = None,
    remote_user: str | None = None,
) -> MigrationResult:
    logger.info("Backing up the database before migration.")
    result = MigrationResult(backup=backup_database(engine))
    logger.info("Migrating database schema.")
    migrate_schema(engine)
    db = DataBaseManager(engine)
    try:
        db.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        works = (
            db.session.query(ASMR.id, ASMR.details.is_(None), ASMR.recovery_ready)
            .filter(or_(ASMR.details.is_(None), ASMR.recovery_ready.is_not(True)))
            .order_by(ASMR.id)
            .all()
        )
        roots = list(dict.fromkeys(roots))
        logger.info("Found %d database works with missing metadata.", len(works))
        for index, (source_id, details_missing, recovery_ready) in enumerate(works, 1):
            source_name = id2source_name(LocalSourceID(source_id))
            logger.info("[%d/%d] Migrating metadata for %s.", index, len(works), source_name)
            if details_missing:
                for root in roots:
                    path = root / source_name / f"{source_name}.json"
                    if not path.is_file():
                        continue
                    try:
                        with db.session.begin_nested():
                            info = json.loads(path.read_text(encoding="utf-8"))
                            if source2id(info["source_id"]) != source_id:
                                raise ValueError("File and work ID do not match.")
                            db.add_info(info, check=False, tag_strategy="accept_all")
                        result.details += 1
                        logger.info("Imported work details for %s.", source_name)
                        break
                    except (
                        OSError, ValueError, TypeError, KeyError,
                        AssertionError, SQLAlchemyError,
                    ) as exc:
                        error = f"{path}: {type(exc).__name__}"
                        result.errors.append(error)
                        if isinstance(exc, (ValueError, TypeError, KeyError, AssertionError)):
                            result.detail_fallbacks[path] = error
            if not recovery_ready:
                for root in roots:
                    path = root / source_name / ".recover"
                    if not path.is_file():
                        continue
                    try:
                        with db.session.begin_nested():
                            records = json.loads(path.read_text(encoding="utf-8"))
                            db.save_recovery(source_id, records)
                        result.recoveries += 1
                        logger.info("Imported recovery records for %s.", source_name)
                    except (OSError, ValueError, TypeError, KeyError, SQLAlchemyError) as exc:
                        result.errors.append(f"{path}: {type(exc).__name__}")
                    break

        if playlist_cache is not None and playlist_cache.is_file():
            logger.info("Importing legacy playlist cache.")
            try:
                cached = toml.load(playlist_cache)["playlists"]
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result.errors.append(f"{playlist_cache}: {type(exc).__name__}")
            else:
                for index, item in enumerate(cached, 1):
                    try:
                        with db.session.begin_nested():
                            remote_id = uuid.UUID(item["id"])
                            existing = (
                                db.session.query(Playlist)
                                .filter_by(remote_id=remote_id)
                                .one_or_none()
                            )
                            if existing is not None:
                                result.skipped += 1
                                continue
                            db.session.add(
                                Playlist(
                                    id=uuid.uuid4(),
                                    remote_id=remote_id,
                                    remote_service=remote_service,
                                    remote_user=remote_user,
                                    name=item["name"],
                                    description=item.get("desc", ""),
                                    privacy=PRIVACY(item["privacy"]).value,
                                    members_complete=False,
                                )
                            )
                        result.playlists += 1
                    except (ValueError, TypeError, KeyError, SQLAlchemyError) as exc:
                        result.errors.append(
                            f"{playlist_cache}: playlist #{index}: {type(exc).__name__}"
                        )
        db.session.commit()
        logger.info("Local metadata migration committed.")
        return result
    except BaseException:
        db.session.rollback()
        raise
    finally:
        db.session.close()
