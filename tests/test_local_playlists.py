import json
import uuid
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from click import Argument, Context
from click.testing import CliRunner
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from asmrmanager.cli.core import get_prev_source, pl_preprocess_cb
from asmrmanager.cli.pl import PLID, pl
from asmrmanager.common.types import PRIVACY
from asmrmanager.config import SyncConfig, config
from asmrmanager.database.database import ASMR, PlaylistWork
from asmrmanager.database.manage import DataBaseManager
from tests.test_local_database import work_info


class LocalPlaylistTest(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'data.db'}")
        self.addCleanup(self.engine.dispose)
        event.listen(
            self.engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
        self.db = DataBaseManager(self.engine)
        self.addCleanup(self.db.session.close)
        for source, remote_id in (
            ("RJ000123", 200123),
            ("VJ000456", 100000456),
            ("BJ000789", 200000789),
        ):
            self.db.add_info(work_info(source, remote_id))
        self.db.session.commit()
        self.enterContext(
            patch("asmrmanager.cli.core.create_database", return_value=self.db)
        )
        self.enterContext(
            patch("asmrmanager.cli.pl.create_database", return_value=self.db)
        )
        self.network = self.enterContext(
            patch(
                "asmrmanager.cli.core.create_api_client",
                side_effect=AssertionError(
                    "Local playlists must not create an API client"
                ),
            )
        )
        self.enterContext(patch.object(config, "sync", SyncConfig()))
        self.enterContext(patch.object(config, "playlist_aliases", {}))
        self.enterContext(
            patch(
                "asmrmanager.cli.core.PREVIOUS_RJ_PATH", self.root / ".prev_rj"
            )
        )
        get_prev_source.cache_clear()
        self.addCleanup(get_prev_source.cache_clear)
        self.enterContext(
            patch(
                "asmrmanager.filemanager.manager.FileManager.CACHE_PATH",
                self.root,
            )
        )
        self.runner = CliRunner()

    def tearDown(self):
        self.network.assert_not_called()

    def playlist(self, name="Local", **kwargs):
        playlist = self.db.create_playlist(name, **kwargs)
        self.db.session.commit()
        return playlist

    def invoke(self, *arguments):
        result = self.runner.invoke(pl, list(arguments))
        self.assertEqual(result.exit_code, 0, result.output)
        return result

    def test_create_has_local_identity_metadata_and_known_empty_members(self):
        playlist = self.playlist(
            description="Description", privacy=PRIVACY.PUBLIC
        )
        self.assertIsInstance(playlist.id, uuid.UUID)
        self.assertIsNone(playlist.remote_id)
        self.assertIsNone(playlist.remote_service)
        self.assertIsNone(playlist.remote_user)
        self.assertEqual(playlist.description, "Description")
        self.assertEqual(playlist.privacy, PRIVACY.PUBLIC.value)
        self.assertTrue(playlist.members_complete)
        self.assertEqual(playlist.works, [])

    def test_duplicate_names_require_a_local_id(self):
        first = self.playlist("Same")
        second = self.playlist("Same")
        with self.assertRaisesRegex(
            ValueError, "Multiple local playlists"
        ) as error:
            self.db.get_playlist("Same")
        self.assertIn(str(first.id), str(error.exception))
        self.assertIn(str(second.id), str(error.exception))
        self.assertIs(self.db.get_playlist(str(second.id)), second)

    def test_invalid_creation_does_not_add_a_playlist(self):
        for name in ("", "  "):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.db.create_playlist(name)
        with self.assertRaises(TypeError):
            self.db.create_playlist("Name", privacy=9)
        self.assertEqual(self.db.list_playlists(), [])

    def test_add_is_idempotent_and_works_can_belong_to_multiple_playlists(
        self,
    ):
        first = self.playlist("First")
        second = self.playlist("Second")
        self.db.add_playlist_works(first.id, [123, 123, 300000456])
        self.db.add_playlist_works(first.id, [123])
        self.db.add_playlist_works(second.id, [123])
        self.db.session.commit()
        self.assertEqual({work.id for work in first.works}, {123, 300000456})
        self.assertEqual([work.id for work in second.works], [123])
        self.assertEqual(self.db.session.query(PlaylistWork).count(), 3)

    def test_member_primary_key_rejects_duplicate_rows(self):
        playlist = self.playlist()
        self.db.add_playlist_works(playlist.id, [123])
        self.db.session.commit()
        self.db.session.add(PlaylistWork(playlist_id=playlist.id, work_id=123))
        with self.assertRaises(IntegrityError):
            self.db.session.commit()
        self.db.session.rollback()
        self.assertEqual([work.id for work in playlist.works], [123])

    def test_foreign_key_rejects_missing_work(self):
        playlist = self.playlist()
        self.db.session.add(PlaylistWork(playlist_id=playlist.id, work_id=999))
        with self.assertRaises(IntegrityError):
            self.db.session.commit()
        self.db.session.rollback()
        self.assertEqual(playlist.works, [])

    def test_add_validates_all_members_before_modifying_the_list(self):
        playlist = self.playlist()
        with self.assertRaisesRegex(ValueError, "999"):
            self.db.add_playlist_works(playlist.id, [123, 999])
        self.db.session.commit()
        self.assertEqual(playlist.works, [])

    def test_remove_validates_all_ids_before_deleting(self):
        playlist = self.playlist()
        with self.assertRaises(ValueError):
            self.db.remove_playlists([playlist.id, uuid.uuid4()])
        self.db.session.commit()
        self.assertIsNotNone(self.db.get_playlist(playlist.id))

    def test_remove_cleans_members_and_keeps_works_and_other_playlists(self):
        first = self.playlist("First")
        second = self.playlist("Second")
        self.db.add_playlist_works(first.id, [123, 300000456])
        self.db.add_playlist_works(second.id, [123])
        self.db.session.commit()
        self.db.remove_playlists([first.id, first.id])
        self.db.session.commit()
        self.assertEqual(self.db.session.query(PlaylistWork).count(), 1)
        self.assertEqual(self.db.session.query(ASMR).count(), 3)
        self.assertEqual([work.id for work in second.works], [123])

    def test_playlist_changes_do_not_update_work_state_or_details(self):
        playlist = self.playlist()
        work = self.db.update_review(
            123, star=4, comment="Comment", progress="listened"
        )
        work.notes, work.held, work.stored = "Private note", True, True
        self.db.session.commit()
        before = (deepcopy(work.details), work.last_review)
        self.db.add_playlist_works(playlist.id, [123])
        self.db.session.commit()
        self.db.remove_playlists([playlist.id])
        self.db.session.commit()
        self.assertEqual((work.details, work.last_review), before)
        self.assertEqual(
            (work.star, work.comment, work.progress),
            (4, "Comment", "listened"),
        )
        self.assertEqual(
            (work.notes, work.held, work.stored), ("Private note", True, True)
        )

    def test_add_to_incomplete_list_does_not_claim_full_membership(self):
        playlist = self.playlist()
        playlist.remote_id = uuid.uuid4()
        playlist.members_complete = False
        self.db.session.commit()
        self.db.add_playlist_works(playlist.id, [123])
        self.db.session.commit()
        self.assertFalse(playlist.members_complete)
        rows = json.loads(self.invoke("list", "--raw").output)
        self.assertEqual(rows[0]["known_members"], 1)
        self.assertFalse(rows[0]["members_complete"])
        self.assertEqual(rows[0]["remote_id"], str(playlist.remote_id))
        result = self.invoke("show", str(playlist.id))
        self.assertIn("membership is incomplete", result.output)
        self.assertIn("RJ000123", result.output)

    def test_local_work_resolution_does_not_need_remote_conversion(self):
        for source, expected in (
            ("RJ000123", 123),
            ("123", 123),
            ("200123", 123),
            ("VJ000456", 300000456),
            ("300000456", 300000456),
            ("100000456", 300000456),
            ("BJ000789", 400000789),
            ("200000789", 400000789),
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    self.db.resolve_local_work(source).id, expected
                )

    def test_explicit_source_name_cannot_resolve_as_a_remote_id(self):
        for source in (
            "RJ200123",
            "RJ100000456",
            "VJ200000789",
            "RJ300000456",
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.db.resolve_local_work(source)

    def test_invalid_and_unknown_works_are_rejected(self):
        for source in (
            "",
            "bad",
            "-1",
            "0",
            "500000123",
            "RJ000999",
            "100000999",
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.db.resolve_local_work(source)

    def test_all_cli_operations_work_offline_without_a_playlist_cache(self):
        self.assertFalse((self.root / "playlist.cache").exists())
        self.invoke(
            "create",
            "Offline",
            "--desc",
            "Offline list",
            "--privacy",
            "NON_PUBLIC",
        )
        playlist = self.db.get_playlist("Offline")
        self.invoke(
            "add", "Offline", "RJ000123", "VJ000456", "BJ000789", "200123"
        )
        rows = json.loads(self.invoke("list", "--raw").output)
        self.assertEqual(
            rows,
            [
                {
                    "id": str(playlist.id),
                    "remote_id": None,
                    "name": "Offline",
                    "description": "Offline list",
                    "known_members": 3,
                    "privacy": "NON_PUBLIC",
                    "members_complete": True,
                }
            ],
        )
        with (
            patch("asmrmanager.cli.pl.support_image", return_value=True),
            patch("asmrmanager.cli.pl.fm") as fm,
        ):
            fm.get_cover_path.return_value = self.root / "cover.jpg"
            result = self.invoke("show", "Offline")
            self.assertIn("RJ000123", result.output)
            self.assertEqual(fm.get_cover_path.call_count, 3)
        self.invoke("rm", str(playlist.id))
        self.assertEqual(self.db.list_playlists(), [])
        self.assertEqual(self.db.session.query(ASMR).count(), 3)
        self.assertFalse((self.root / "playlist.cache").exists())

    def test_legacy_cache_is_not_read_or_overwritten(self):
        cache = self.root / "playlist.cache"
        cache.write_text("invalid legacy TOML [")
        self.assertEqual(json.loads(self.invoke("list", "--raw").output), [])
        self.invoke("create", "Local")
        self.invoke("add", "Local", "RJ000123")
        self.invoke("show", "Local")
        PLID().shell_complete(Context(pl), Argument(["pl_id"]), "")
        self.invoke("rm", "Local")
        self.assertEqual(cache.read_text(), "invalid legacy TOML [")

    def test_linked_playlists_can_change_locally_when_sync_is_disabled(self):
        playlist = self.playlist()
        playlist.remote_id = uuid.uuid4()
        playlist.members_complete = False
        self.db.session.commit()
        remote_id = playlist.remote_id
        self.invoke("add", str(playlist.id), "RJ000123")
        self.assertEqual(playlist.remote_id, remote_id)
        self.assertFalse(playlist.members_complete)
        self.invoke("rm", str(playlist.id))
        self.assertEqual(self.db.session.query(ASMR).count(), 3)

    def test_cli_resolves_aliases_to_names_and_local_ids(self):
        playlist = self.playlist("Unique")
        config.playlist_aliases = {
            "by-name": "Unique",
            "by-id": str(playlist.id),
        }
        self.invoke("add", "by-name", "RJ000123")
        self.invoke("show", "by-id")
        self.invoke("rm", "by-id")
        self.assertEqual(self.db.list_playlists(), [])

    def test_cli_does_not_ignore_unknown_playlists_in_a_batch(self):
        playlist = self.playlist()
        result = self.runner.invoke(pl, ["rm", str(playlist.id), "Missing"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not found", result.output)
        self.assertEqual(len(self.db.list_playlists()), 1)

    def test_cli_duplicate_names_reject_name_but_accept_id(self):
        first = self.playlist("Same")
        second = self.playlist("Same")
        result = self.runner.invoke(pl, ["add", "Same", "RJ000123"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Multiple local playlists", result.output)
        self.invoke("add", str(second.id), "RJ000123")
        self.assertEqual(first.works, [])
        self.assertEqual([work.id for work in second.works], [123])

    def test_cli_requires_a_playlist_for_removal(self):
        self.playlist()
        result = self.runner.invoke(pl, ["rm"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Specify at least one", result.output)
        self.assertEqual(len(self.db.list_playlists()), 1)

    def test_cli_invalid_source_does_not_add_any_members_or_change_previous(
        self,
    ):
        playlist = self.playlist()
        previous = self.root / ".prev_rj"
        previous.write_text("RJ000123")
        for source in ("RJ000999", "invalid", "100000999"):
            with self.subTest(source=source):
                result = self.runner.invoke(
                    pl, ["add", str(playlist.id), "VJ000456", source]
                )
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(playlist.works, [])
                self.assertEqual(previous.read_text(), "RJ000123")

    def test_cli_uses_previous_source_when_none_is_specified(self):
        playlist = self.playlist()
        self.invoke("add", str(playlist.id), "VJ000456")
        self.invoke("add", str(playlist.id))
        self.assertEqual([work.id for work in playlist.works], [300000456])
        self.invoke("add", str(playlist.id), "BJ000789")
        second = self.playlist("Second")
        self.invoke("add", str(second.id))
        self.assertEqual([work.id for work in second.works], [400000789])

    def test_cli_without_previous_source_reports_error(self):
        playlist = self.playlist()
        result = self.runner.invoke(pl, ["add", str(playlist.id)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid work ID", result.output)
        self.assertEqual(playlist.works, [])

    def test_commit_failures_roll_back_create_add_and_remove(self):
        playlist = self.playlist()
        for arguments in (
            ["create", "Not saved"],
            ["add", str(playlist.id), "RJ000123"],
            ["rm", str(playlist.id)],
        ):
            with (
                self.subTest(arguments=arguments),
                patch.object(
                    self.db.session,
                    "commit",
                    side_effect=SQLAlchemyError("failed"),
                ),
            ):
                result = self.runner.invoke(pl, arguments)
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn(
                    "Could not save local playlist changes", result.output
                )
            self.assertEqual(
                [item.id for item in self.db.list_playlists()], [playlist.id]
            )
            self.assertEqual(playlist.works, [])
            self.assertFalse((self.root / ".prev_rj").exists())

    def test_enabled_playlist_sync_blocks_unimplemented_cloud_writes(self):
        playlist = self.playlist()
        config.sync.playlist = True
        for arguments in (
            ["create", "No implicit publishing"],
            ["add", str(playlist.id), "RJ000123"],
            ["rm", str(playlist.id)],
        ):
            with self.subTest(arguments=arguments):
                result = self.runner.invoke(pl, arguments)
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn(
                    "cloud synchronization is not available", result.output
                )
        self.assertEqual(len(self.db.list_playlists()), 1)
        self.assertEqual(playlist.works, [])
        self.assertIsNone(playlist.remote_id)
        self.invoke("list", "--raw")
        self.invoke("show", str(playlist.id))

    def test_completions_offer_ids_unique_names_and_valid_aliases(self):
        unique = self.playlist("Unique", description="Description")
        first = self.playlist("Same")
        second = self.playlist("Same")
        config.playlist_aliases = {
            "valid": str(unique.id),
            "unique-name": "Unique",
            "ambiguous": "Same",
            "missing": "Missing",
        }
        values = {
            item.value
            for item in PLID().shell_complete(
                Context(pl), Argument(["pl_id"]), ""
            )
        }
        self.assertEqual(
            values,
            {
                str(unique.id),
                str(first.id),
                str(second.id),
                "Unique",
                "valid",
                "unique-name",
            },
        )
        matches = PLID().shell_complete(Context(pl), Argument(["pl_id"]), "UN")
        self.assertEqual(
            {item.value for item in matches}, {"Unique", "unique-name"}
        )

    def test_resilient_parameter_parsing_does_not_open_a_database(self):
        with patch(
            "asmrmanager.cli.core.create_database",
            side_effect=AssertionError("No lookup during resilient parsing"),
        ):
            result = pl_preprocess_cb(
                Context(pl, resilient_parsing=True),
                Argument(["pl_id"]),
                "partial",
            )
        self.assertIsNone(result)

    def test_unknown_local_id_is_not_assumed_to_be_a_cloud_id(self):
        playlist = self.playlist()
        playlist.remote_id = uuid.uuid4()
        self.db.session.commit()
        result = self.runner.invoke(pl, ["show", str(playlist.remote_id)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Local playlist", result.output)

    def test_list_limit_is_positive_and_deterministic(self):
        self.playlist("Z")
        self.playlist("A")
        rows = json.loads(self.invoke("list", "--num", "1", "--raw").output)
        self.assertEqual([item["name"] for item in rows], ["A"])
        result = self.runner.invoke(pl, ["list", "--num", "0"])
        self.assertNotEqual(result.exit_code, 0)

    def test_empty_database_has_empty_lists_and_completions(self):
        self.assertEqual(json.loads(self.invoke("list", "--raw").output), [])
        values = PLID().shell_complete(Context(pl), Argument(["pl_id"]), "")
        self.assertEqual(values, [])
