import json
import sqlite3
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import toml
from click.testing import CliRunner
from sqlalchemy import create_engine, inspect

from asmrmanager.cli.review import review
from asmrmanager.cli.utils import migrate
from asmrmanager.common.types import validate_recovery
from asmrmanager.database.database import (
    ASMR,
    ASMRs2Tags,
    ASMRs2VAs,
    History,
    Playlist,
    Tag,
    VoiceActor,
)
from asmrmanager.database.manage import DataBaseManager
from asmrmanager.database.migrate import migrate_database, migrate_schema


def work_info(source="RJ000123", remote_id=200123):
    return {
        "id": remote_id,
        "source_id": source,
        "title": "Test work",
        "name": "Test circle",
        "nsfw": False,
        "release": "2024-01-02",
        "price": 100,
        "dl_count": 20,
        "has_subtitle": True,
        "vas": [
            {"id": "00000000-0000-0000-0000-000000000001", "name": "Actor"}
        ],
        "tags": [
            {
                "id": 10,
                "name": "Tag",
                "upvote": 1,
                "downvote": 0,
                "myVote": 0,
                "voteStatus": 1,
                "i18n": {
                    locale: {"name": "Tag"}
                    for locale in ("zh-cn", "ja-jp", "en-us")
                },
            }
        ],
        "extra_cloud_field": {"keep": [1, 2, 3]},
    }


def recovery(path="audio/track.mp3", file_id=100):
    return {
        "path": path,
        "url": "https://example.com/audio",
        "should_download": True,
        "fileId": file_id,
    }


class DatabaseTest(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'data.db'}")
        self.addCleanup(self.engine.dispose)

    def database(self):
        db = DataBaseManager(self.engine)
        self.addCleanup(db.session.close)
        return db

    def legacy(self, remote_column=True):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE asmr (id INTEGER PRIMARY KEY, "
                + ("remote_id INTEGER UNIQUE, " if remote_column else "")
                + "title TEXT, circle_name TEXT, nsfw BOOLEAN, release_date DATE, "
                "price INTEGER, dl_count INTEGER, has_subtitle BOOLEAN, "
                "star INTEGER DEFAULT 0, count INTEGER DEFAULT 0, "
                "comment TEXT DEFAULT '', held BOOLEAN DEFAULT 0, stored BOOLEAN DEFAULT 0)"
            )
            connection.exec_driver_sql(
                "INSERT INTO asmr (id, title, star, count, comment, held, stored) "
                "VALUES (123, 'Legacy', 4, 3, '2024-02-03: old review', 1, 1)"
            )
            if remote_column:
                connection.exec_driver_sql(
                    "UPDATE asmr SET remote_id = 200123"
                )

    def test_migrate_cli_reports_backup_and_import_results(self):
        self.legacy()
        with (
            patch(
                "asmrmanager.database.engine.get_engine",
                return_value=self.engine,
            ),
            patch("asmrmanager.cli.utils.fm") as fm,
        ):
            fm.CACHE_PATH = self.root
            result = CliRunner().invoke(migrate, ["--root", str(self.root)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Database backup:", result.output)
        self.assertIn("Legacy files were kept", result.output)

    def test_migrate_cli_reports_bad_files_as_failure(self):
        (self.root / "RJ000123.json").write_text("bad JSON")
        with (
            patch(
                "asmrmanager.database.engine.get_engine",
                return_value=self.engine,
            ),
            patch("asmrmanager.cli.utils.fm") as fm,
        ):
            fm.CACHE_PATH = self.root
            result = CliRunner().invoke(migrate, ["--root", str(self.root)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("1 legacy imports failed", result.output)
        self.assertTrue((self.root / "RJ000123.json").exists())

    def test_migration_preserves_existing_relations_and_history(self):
        self.legacy()
        for model in (Tag, VoiceActor, ASMRs2Tags, ASMRs2VAs, History):
            model.__table__.create(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO tag (id, name) VALUES (10, 'Tag')"
            )
            connection.exec_driver_sql(
                "INSERT INTO voice_actor (id, name) VALUES ('00000000000000000000000000000001', 'Actor')"
            )
            connection.exec_driver_sql(
                "INSERT INTO asmrs2tags (asmr_id, tag_id) VALUES (123, 10)"
            )
            connection.exec_driver_sql(
                "INSERT INTO asmrs2vas (asmr_id, actor_id) VALUES (123, '00000000000000000000000000000001')"
            )
            connection.exec_driver_sql(
                "INSERT INTO history (asmr_id, date, finish) VALUES (123, '2024-01-02', 1)"
            )
        migrate_database(self.engine, [])
        db = self.database()
        work = db.session.get(ASMR, 123)
        self.assertEqual([tag.id for tag in work.tags], [10])
        self.assertEqual([actor.name for actor in work.vas], ["Actor"])
        self.assertEqual(len(work.histories), 1)
        self.assertTrue(work.histories[0].finish)

    def test_import_legacy_tags_without_vote_or_translation_fields(self):
        info = work_info()
        info["tags"] = [{"id": 10, "name": "Legacy tag"}]
        (self.root / "RJ000123.json").write_text(json.dumps(info))
        result = migrate_database(self.engine, [self.root])
        self.assertEqual(result.errors, [])
        self.assertEqual(result.details, 1)
        self.assertEqual(
            self.database().session.get(ASMR, 123).tags[0].name, "Legacy tag"
        )

    def test_duplicate_remote_id_is_reported_without_losing_other_imports(
        self,
    ):
        (self.root / "RJ000123.json").write_text(json.dumps(work_info()))
        (self.root / "RJ000124.json").write_text(
            json.dumps(work_info("RJ000124"))
        )
        result = migrate_database(self.engine, [self.root])
        self.assertEqual(result.details, 1)
        self.assertEqual(len(result.errors), 1)
        db = self.database()
        self.assertIsNotNone(db.session.get(ASMR, 123))
        self.assertIsNone(db.session.get(ASMR, 124))

    def test_new_database_has_latest_schema(self):
        db = self.database()
        self.assertTrue(db.check_db_updated())
        self.assertNotIn(
            "count",
            {
                column["name"]
                for column in inspect(self.engine).get_columns("asmr")
            },
        )

    def test_opening_legacy_does_not_change_schema(self):
        self.legacy()
        before = inspect(self.engine).get_table_names()
        db = self.database()
        self.assertFalse(db.check_db_updated())
        self.assertEqual(before, inspect(self.engine).get_table_names())

    def test_legacy_backup_and_review_migration(self):
        self.legacy()
        result = migrate_database(self.engine, [])
        self.assertTrue(result.backup.is_file())
        with sqlite3.connect(result.backup) as backup:
            row = backup.execute("SELECT count, comment FROM asmr").fetchone()
            self.assertEqual(row, (3, "2024-02-03: old review"))
        db = self.database()
        self.assertTrue(db.check_db_updated())
        work = db.session.get(ASMR, 123)
        self.assertEqual(work.notes, "2024-02-03: old review")
        self.assertEqual(work.comment, "")
        self.assertEqual(work.star, 4)
        self.assertIsNone(work.last_review)
        self.assertTrue(work.held)
        self.assertTrue(work.stored)

    def test_backup_includes_wal_data(self):
        self.legacy()
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode = WAL")
            connection.exec_driver_sql("UPDATE asmr SET star = 5")
            connection.commit()
            result = migrate_database(self.engine, [])
        with sqlite3.connect(result.backup) as backup:
            self.assertEqual(
                backup.execute("SELECT star FROM asmr").fetchone()[0], 5
            )

    def test_empty_database_migration(self):
        result = migrate_database(self.engine, [])
        self.assertIsNone(result.backup)
        self.assertTrue(self.database().check_db_updated())

    def test_old_remote_id_migration(self):
        self.legacy(remote_column=False)
        migrate_database(self.engine, [])
        self.assertEqual(self.database().session.get(ASMR, 123).remote_id, 123)

    def test_migration_is_idempotent_and_keeps_new_review(self):
        self.legacy()
        migrate_database(self.engine, [])
        db = self.database()
        db.update_review(
            123, star=5, comment="New comment", progress="listening"
        )
        db.session.get(ASMR, 123).notes += "\nNew note"
        db.session.commit()
        migrate_database(self.engine, [])
        db.session.expire_all()
        work = db.session.get(ASMR, 123)
        self.assertEqual(work.star, 5)
        self.assertEqual(work.comment, "New comment")
        self.assertEqual(work.progress, "listening")
        self.assertEqual(work.notes, "2024-02-03: old review\nNew note")
        self.assertEqual(
            work.last_review, datetime.now(UTC).astimezone().date()
        )

    def test_backup_failure_does_not_change_schema(self):
        self.legacy()
        with (
            patch(
                "asmrmanager.database.migrate.backup_database",
                side_effect=OSError("denied"),
            ),
            self.assertRaises(OSError),
        ):
            migrate_database(self.engine, [])
        self.assertIn(
            "count",
            {
                column["name"]
                for column in inspect(self.engine).get_columns("asmr")
            },
        )
        self.assertNotIn(
            "notes",
            {
                column["name"]
                for column in inspect(self.engine).get_columns("asmr")
            },
        )

    def test_schema_failure_rolls_back(self):
        self.legacy()
        with (
            patch(
                "asmrmanager.database.migrate.Base.metadata.create_all",
                side_effect=RuntimeError("fail"),
            ),
            self.assertRaises(RuntimeError),
        ):
            migrate_schema(self.engine)
        names = {
            column["name"]
            for column in inspect(self.engine).get_columns("asmr")
        }
        self.assertIn("count", names)
        self.assertNotIn("notes", names)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.exec_driver_sql(
                    "SELECT comment FROM asmr"
                ).scalar(),
                "2024-02-03: old review",
            )

    def test_newer_schema_is_rejected(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA user_version = 99")
        with self.assertRaises(ValueError):
            migrate_schema(self.engine)

    def test_opening_newer_schema_does_not_overwrite_version(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA user_version = 99")
        with self.assertRaises(ValueError):
            self.database()
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.exec_driver_sql("PRAGMA user_version").scalar(), 99
            )
        self.assertEqual(inspect(self.engine).get_table_names(), [])

    def test_unexpected_import_failure_rolls_back_imported_data(self):
        source = self.root / "download" / "RJ000123"
        source.mkdir(parents=True)
        (source / "RJ000123.json").write_text(json.dumps(work_info()))
        (source / ".recover").write_text(json.dumps([recovery()]))
        with (
            patch.object(
                DataBaseManager,
                "save_recovery",
                side_effect=RuntimeError("failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            migrate_database(self.engine, [source.parent])
        self.assertIsNone(self.database().session.get(ASMR, 123))

    def test_import_details_recovery_and_cache(self):
        self.legacy()
        source = self.root / "download" / "RJ000123"
        source.mkdir(parents=True)
        details = source / "RJ000123.json"
        recover = source / ".recover"
        details.write_text(json.dumps(work_info()))
        recover.write_text(json.dumps([recovery()]))
        remote_id = uuid.uuid4()
        cache = self.root / "playlist.cache"
        cache.write_text(
            toml.dumps(
                {
                    "playlists": [
                        {
                            "id": str(remote_id),
                            "name": "List",
                            "desc": "Description",
                            "privacy": 0,
                            "works_count": 4,
                        }
                    ]
                }
            )
        )
        result = migrate_database(self.engine, [source.parent], cache)
        self.assertEqual(result.errors, [])
        self.assertEqual(
            (result.details, result.recoveries, result.playlists), (1, 1, 1)
        )
        db = self.database()
        self.assertEqual(db.load_recovery(123), [recovery()])
        self.assertEqual(db.session.get(ASMR, 123).details, work_info())
        self.assertEqual(db.session.get(ASMR, 123).star, 4)
        playlist = db.session.query(Playlist).one()
        self.assertEqual(playlist.remote_id, remote_id)
        self.assertNotEqual(playlist.id, remote_id)
        self.assertFalse(playlist.members_complete)
        self.assertTrue(details.exists())
        self.assertTrue(recover.exists())
        second = migrate_database(self.engine, [source.parent], cache)
        self.assertEqual(
            (second.details, second.recoveries, second.playlists), (0, 0, 0)
        )

    def test_download_recovery_takes_precedence(self):
        self.database().session.close()
        for name, file_id in (("download", 101), ("storage", 102)):
            source = self.root / name / "RJ000123"
            source.mkdir(parents=True)
            (source / "RJ000123.json").write_text(json.dumps(work_info()))
            (source / ".recover").write_text(
                json.dumps([recovery(file_id=file_id)])
            )
        migrate_database(
            self.engine, [self.root / "download", self.root / "storage"]
        )
        self.assertEqual(self.database().load_recovery(123)[0]["fileId"], 101)

    def test_corrupt_import_reports_failure_without_clearing_state(self):
        db = self.database()
        db.add_info(work_info())
        db.save_recovery(123, [recovery()])
        db.session.commit()
        source = self.root / "RJ000123"
        source.mkdir()
        (source / ".recover").write_text("not JSON")
        broken = self.root / "RJ000124.json"
        broken.write_text("not JSON")
        result = migrate_database(self.engine, [self.root])
        self.assertEqual(len(result.errors), 1)
        db.session.expire_all()
        self.assertEqual(db.load_recovery(123), [recovery()])

    def test_details_retained_before_tag_filter(self):
        db = self.database()
        info = work_info()
        info["tags"][0]["voteStatus"] = 2
        snapshot = deepcopy(info)
        db.add_info(info)
        db.session.commit()
        work = db.session.get(ASMR, 123)
        self.assertEqual(info, snapshot)
        self.assertEqual(work.details, snapshot)
        self.assertEqual(work.tags, [])

    def test_metadata_update_preserves_user_state(self):
        db = self.database()
        db.add_info(work_info())
        db.update_review(123, 5, "My comment", progress="listening")
        work = db.session.get(ASMR, 123)
        work.notes = "Private note"
        work.held = work.stored = True
        db.session.commit()
        db.add_info({**work_info(), "title": "Changed"})
        db.session.commit()
        work = db.session.get(ASMR, 123)
        self.assertEqual(
            (work.star, work.comment, work.progress, work.notes),
            (5, "My comment", "listening", "Private note"),
        )
        self.assertEqual(work.title, "Changed")
        self.assertTrue(work.held and work.stored)
        self.assertEqual(
            work.last_review, datetime.now(UTC).astimezone().date()
        )

    def test_comment_replacement_and_local_hold_note(self):
        db = self.database()
        db.add_info(work_info())
        db.update_review(123, comment="First")
        db.update_review(123, comment="Second")
        db.hold_item(123, "Private reason")
        work = db.session.get(ASMR, 123)
        self.assertEqual(work.comment, "Second")
        self.assertIn("Private reason", work.notes)
        db.update_review(123, star=0, comment="")
        self.assertEqual((work.star, work.comment), (0, ""))

    def test_progress_and_clear_do_not_change_review_date(self):
        db = self.database()
        db.add_info(work_info())
        work = db.update_review(123, progress="listened", update_stored=True)
        self.assertIsNone(work.last_review)
        self.assertFalse(work.stored)
        db.update_review(123, clear_progress=True)
        self.assertIsNone(work.progress)
        self.assertIsNone(work.last_review)

    def test_invalid_review_is_atomic(self):
        db = self.database()
        db.add_info(work_info())
        work = db.update_review(123, star=4)
        for values in (
            {"star": 6},
            {"star": True},
            {"star": 5, "progress": "unknown"},
            {"progress": "listening", "clear_progress": True},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                db.update_review(123, **values)
            self.assertEqual(work.star, 4)
            self.assertIsNone(work.progress)

    def test_recovery_replaces_only_one_work_and_handles_empty(self):
        db = self.database()
        db.add_info(work_info())
        db.add_info(work_info("VJ000456", 100456))
        db.save_recovery(123, [recovery()])
        db.save_recovery(300000456, [recovery()])
        db.session.commit()
        db.save_recovery(123, [])
        db.session.commit()
        self.assertEqual(db.load_recovery(123), [])
        self.assertEqual(db.load_recovery(300000456), [recovery()])
        self.assertIsNone(db.load_recovery(999))

    def test_invalid_recovery_does_not_remove_existing_records(self):
        db = self.database()
        db.add_info(work_info())
        db.save_recovery(123, [recovery()])
        db.session.commit()
        with self.assertRaises(ValueError):
            db.save_recovery(123, [recovery("../audio.mp3")])
        self.assertEqual(db.load_recovery(123), [recovery()])

    def test_review_cli_progress_never_moves_files(self):
        db = self.database()
        db.add_info(work_info())
        db.session.commit()
        with (
            patch("asmrmanager.cli.review.create_database", return_value=db),
            patch("asmrmanager.cli.review.fm") as fm,
        ):
            result = CliRunner().invoke(
                review, ["RJ000123", "--progress", "listening"]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            fm.store.assert_not_called()
        self.assertEqual(db.session.get(ASMR, 123).progress, "listening")

    def test_review_cli_validates_before_moving_files(self):
        db = self.database()
        with (
            patch("asmrmanager.cli.review.create_database", return_value=db),
            patch("asmrmanager.cli.review.fm") as fm,
        ):
            result = CliRunner().invoke(review, ["RJ000999", "--star", "5"])
            self.assertNotEqual(result.exit_code, 0)
            fm.store.assert_not_called()

    def test_review_cli_storage_failure_rolls_back_pending_review(self):
        db = self.database()
        db.add_info(work_info())
        db.session.commit()
        with (
            patch("asmrmanager.cli.review.create_database", return_value=db),
            patch("asmrmanager.cli.review.fm") as fm,
        ):
            fm.could_store.return_value = True
            fm.get_location.return_value = "download"
            fm.store.side_effect = OSError("storage failed")
            result = CliRunner().invoke(
                review, ["RJ000123", "--star", "5", "--comment", "Not saved"]
            )
        self.assertNotEqual(result.exit_code, 0)
        work = db.session.get(ASMR, 123)
        self.assertEqual(work.star, 0)
        self.assertEqual(work.comment, "")
        self.assertIsNone(work.last_review)
        self.assertFalse(work.stored)

    def test_review_cli_rating_updates_stored_state(self):
        db = self.database()
        db.add_info(work_info())
        db.session.commit()
        with (
            patch("asmrmanager.cli.review.create_database", return_value=db),
            patch("asmrmanager.cli.review.fm") as fm,
        ):
            fm.could_store.return_value = True
            fm.get_location.side_effect = ["download", "storage"]
            result = CliRunner().invoke(review, ["RJ000123", "--star", "5"])
            self.assertEqual(result.exit_code, 0, result.output)
            fm.store.assert_called_once_with(123)
        self.assertTrue(db.session.get(ASMR, 123).stored)


class RecoveryValidationTest(TestCase):
    def test_rejects_unsafe_and_duplicate_paths(self):
        for path in (
            "/audio.mp3",
            "../audio.mp3",
            "audio/../../x",
            "C:\\audio.mp3",
            ".",
            "",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_recovery([recovery(path)])
        with self.assertRaises(ValueError):
            validate_recovery([recovery(), recovery()])

    def test_normalizes_windows_relative_paths(self):
        self.assertEqual(
            validate_recovery([recovery("audio\\track.mp3")])[0]["path"],
            "audio/track.mp3",
        )

    def test_accepts_missing_legacy_file_id(self):
        record = recovery()
        del record["fileId"]
        self.assertEqual(validate_recovery([record]), [record])

    def test_rejects_invalid_records(self):
        for record in (
            [{"path": "x"}],
            [recovery(file_id=True)],
            [recovery(file_id=0)],
            [{**recovery(), "should_download": 1}],
        ):
            with self.subTest(record=record), self.assertRaises(ValueError):
                validate_recovery(record)
        for records in ([None], {}):
            with self.subTest(records=records), self.assertRaises(TypeError):
                validate_recovery(records)
