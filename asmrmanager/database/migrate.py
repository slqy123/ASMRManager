import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile

import toml
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from asmrmanager.common.rj_parse import source2id
from asmrmanager.common.types import PRIVACY

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
    result = MigrationResult(backup=backup_database(engine))
    migrate_schema(engine)
    db = DataBaseManager(engine)
    try:
        db.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        for root in dict.fromkeys(roots):
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.json")):
                source_id = source2id(path.stem)
                if (
                    not path.stem.startswith(("RJ", "VJ", "BJ"))
                    or source_id is None
                ):
                    continue
                try:
                    with db.session.begin_nested():
                        existing = db.session.get(ASMR, source_id)
                        if (
                            existing is not None
                            and existing.details is not None
                        ):
                            result.skipped += 1
                            continue
                        info = json.loads(path.read_text(encoding="utf-8"))
                        if source2id(info["source_id"]) != source_id:
                            raise ValueError("File and work ID do not match.")
                        db.add_info(
                            info, check=False, tag_strategy="accept_all"
                        )
                    result.details += 1
                except (
                    OSError,
                    ValueError,
                    TypeError,
                    KeyError,
                    AssertionError,
                    SQLAlchemyError,
                ) as exc:
                    result.errors.append(f"{path}: {type(exc).__name__}")

        seen = set()
        for root in dict.fromkeys(roots):
            if not root.is_dir():
                continue
            for path in sorted(root.rglob(".recover")):
                source_id = source2id(path.parent.name)
                if source_id is None:
                    result.errors.append(f"{path}: Invalid work directory")
                    continue
                if source_id in seen:
                    result.skipped += 1
                    continue
                seen.add(source_id)
                try:
                    with db.session.begin_nested():
                        existing = db.session.get(ASMR, source_id)
                        if existing is not None and existing.recovery_ready:
                            result.skipped += 1
                            continue
                        records = json.loads(path.read_text(encoding="utf-8"))
                        db.save_recovery(source_id, records)
                    result.recoveries += 1
                except (
                    OSError,
                    ValueError,
                    TypeError,
                    KeyError,
                    SQLAlchemyError,
                ) as exc:
                    result.errors.append(f"{path}: {type(exc).__name__}")

        if playlist_cache is not None and playlist_cache.is_file():
            try:
                cached = toml.load(playlist_cache)["playlists"]
                for item in cached:
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
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                SQLAlchemyError,
            ) as exc:
                result.errors.append(f"{playlist_cache}: {type(exc).__name__}")
        db.session.commit()
        return result
    except BaseException:
        db.session.rollback()
        raise
    finally:
        db.session.close()
