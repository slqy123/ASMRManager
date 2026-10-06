from copy import deepcopy
from datetime import date
from unittest import TestCase
from unittest.mock import patch

from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from asmrmanager.cli.main import main
from asmrmanager.config import SyncConfig, config
from asmrmanager.database.database import ASMR, Playlist
from asmrmanager.database.manage import DataBaseManager
from asmrmanager.spider.asmrapi import APIError
from asmrmanager.sync import CloudSync, SyncError
from tests.fake_cloud import FakeCloud
from tests.test_local_database import work_info


class CloudSyncTest(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.db = DataBaseManager(self.engine)
        self.addCleanup(self.db.session.close)
        self.infos = [
            work_info(),
            work_info("VJ000456", 100000456),
            work_info("BJ000789", 200000789),
        ]
        for info in self.infos:
            self.db.add_info(info)
        for work in self.db.session.query(ASMR):
            work.star, work.comment, work.progress = 2, "Local", "marked"
            work.last_review, work.notes, work.held, work.stored = (
                date(2001, 2, 3),
                "TEST_PRIVATE_NOTE",
                True,
                True,
            )
        self.db.commit()
        self.api = FakeCloud(self.infos)
        self.runner = CliRunner()
        self.enterContext(patch.object(config, "sync", SyncConfig()))
        self.enterContext(patch.object(config, "playlist_aliases", {}))
        for path in ("core", "review", "pl", "sync"):
            self.enterContext(
                patch(
                    f"asmrmanager.cli.{path}.create_database",
                    return_value=self.db,
                )
            )
        self.network = self.enterContext(
            patch(
                "asmrmanager.cli.core.create_api_client", return_value=self.api
            )
        )
        self.enterContext(patch("asmrmanager.cli.core.save_source"))
        self.fm = self.enterContext(patch("asmrmanager.cli.review.fm"))
        self.fm.could_store.return_value = False

    def invoke(self, *args, **kwargs):
        return self.runner.invoke(main, list(args), **kwargs)

    def ok(self, *args, **kwargs):
        result = self.invoke(*args, **kwargs)
        self.assertEqual(result.exit_code, 0, result.output)
        return result

    def work(self, local_id=123):
        self.db.session.expire_all()
        return self.db.session.get(ASMR, local_id)

    def state(self, work=None):
        work = work or self.work()
        return (
            work.star,
            work.comment,
            work.progress,
            work.last_review,
            work.notes,
            work.held,
            work.stored,
            deepcopy(work.details),
        )

    def review(self, remote_id=200123, **values):
        self.api.reviews[remote_id] = {
            "user_name": self.api.user,
            "userRating": 4,
            "review_text": "Cloud",
            "progress": "replay",
            "updated_at": "2024-01-02",
            **values,
        }

    def linked(self, members=(), name="Linked"):
        remote_id = self.api.playlist(
            name, [self.db.session.get(ASMR, key).remote_id for key in members]
        )
        playlist = self.db.create_playlist(name)
        playlist.remote_id, playlist.remote_service, playlist.remote_user = (
            remote_id,
            self.api.base_api_url.rstrip("/"),
            self.api.user,
        )
        self.db.add_playlist_works(playlist.id, members)
        self.db.commit()
        return playlist

    def writes(self):
        return [
            event for event in self.api.events if event[0] in ("PUT", "POST")
        ]

    def test_review_only_pushes_enabled_submitted_fields(self):
        for fields in (
            ("star",),
            ("comment",),
            ("progress",),
            ("star", "comment"),
            ("star", "progress"),
            ("comment", "progress"),
            ("star", "comment", "progress"),
        ):
            with self.subTest(fields=fields):
                self.review()
                config.sync = SyncConfig(**{name: True for name in fields})
                before = deepcopy(self.api.reviews[200123])
                self.ok(
                    "review",
                    "RJ000123",
                    "--star",
                    "5",
                    "--comment",
                    "Current",
                    "--progress",
                    "listening",
                )
                expected = {
                    **before,
                    **{
                        {
                            "star": "userRating",
                            "comment": "review_text",
                            "progress": "progress",
                        }[name]: {
                            "star": 5,
                            "comment": "Current",
                            "progress": "listening",
                        }[name]
                        for name in fields
                    },
                }
                self.assertEqual(self.api.reviews[200123], expected)
                self.assertEqual(
                    (
                        self.work().star,
                        self.work().comment,
                        self.work().progress,
                    ),
                    (5, "Current", "listening"),
                )
                self.assertEqual(self.work().notes, "TEST_PRIVATE_NOTE")

    def test_retry_uses_current_values_without_local_side_effects(self):
        config.sync = SyncConfig(star=True, comment=True, progress=True)
        for source, key, remote_id in (
            ("RJ000123", 123, 200123),
            ("VJ000456", 300000456, 100000456),
            ("BJ000789", 400000789, 200000789),
        ):
            with self.subTest(source=source):
                work = self.db.session.get(ASMR, key)
                work.star, work.comment, work.progress = 0, "", None
                self.db.commit()
                before = self.state(work)
                self.ok("sync", "push", source)
                self.assertEqual(self.state(self.work(key)), before)
                self.assertEqual(
                    self.api.reviews[remote_id]["userRating"], None
                )
                self.assertEqual(
                    self.api.reviews[remote_id]["review_text"], ""
                )
                self.assertEqual(self.api.reviews[remote_id]["progress"], None)
        self.fm.store.assert_not_called()

    def test_retry_only_selected_enabled_fields_and_disabled_types_stay_offline(
        self,
    ):
        config.sync = SyncConfig(comment=True)
        self.ok("sync", "push", "RJ000123", "--field", "comment")
        self.assertEqual(
            set(self.writes()[-1][2]["data"]), {"work_id", "review_text"}
        )
        self.network.reset_mock()
        self.assertNotEqual(
            self.invoke(
                "sync", "push", "RJ000123", "--field", "star"
            ).exit_code,
            0,
        )
        self.network.assert_not_called()
        config.sync = SyncConfig()
        self.ok("sync", "pull")
        self.assertNotEqual(
            self.invoke("sync", "push", "RJ000123").exit_code, 0
        )
        self.network.assert_not_called()

    def test_account_or_work_mapping_mismatch_cannot_write(self):
        config.sync.star = True
        before = self.state()
        for failure in ("account", "mapping", "missing"):
            with self.subTest(failure=failure):
                self.api.events.clear()
                self.api.user = (
                    "other-user" if failure == "account" else "test-user"
                )
                self.api.works[200123]["source_id"] = (
                    "RJ000999" if failure == "mapping" else "RJ000123"
                )
                self.work().remote_id = (
                    None if failure == "missing" else 200123
                )
                self.db.commit()
                result = self.invoke("sync", "push", "RJ000123")
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(self.writes(), [])
                self.assertEqual(self.state()[:7], before[:7])

    def test_cloud_failure_retains_local_review_and_retry_date(self):
        config.sync.comment = True
        self.api.failures["PUT", "review"] = APIError("TEST_PRIVATE_TOKEN")
        result = self.invoke("review", "RJ000123", "--comment", "Changed")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("changes were saved", result.output)
        self.assertNotIn("TEST_PRIVATE", result.output)
        saved = self.state()
        result = self.invoke("sync", "push", "RJ000123")
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(self.state(), saved)
        self.assertEqual(len(self.writes()), 2)

    def test_publish_initial_members_and_protect_duplicate_publication(self):
        config.sync.playlist = True
        playlist = self.db.create_playlist("Publish")
        self.db.add_playlist_works(playlist.id, [123, 300000456, 400000789])
        self.db.commit()
        self.ok("pl", "publish", str(playlist.id))
        self.assertIsNotNone(playlist.remote_id)
        self.assertTrue(playlist.members_complete)
        self.assertEqual(playlist.remote_user, "test-user")
        self.assertEqual(playlist.remote_service, "https://test.example/api")
        self.assertEqual(
            set(self.api.members[str(playlist.remote_id)]),
            {200123, 100000456, 200000789},
        )
        count = len(self.writes())
        self.assertNotEqual(
            self.invoke("pl", "publish", str(playlist.id)).exit_code, 0
        )
        self.assertEqual(len(self.writes()), count)

    def test_publish_incomplete_local_members_and_disabled_publish_are_rejected(
        self,
    ):
        playlist = self.db.create_playlist("Unknown")
        playlist.members_complete = False
        self.db.commit()
        for enabled in (False, True):
            config.sync.playlist = enabled
            self.assertNotEqual(
                self.invoke("pl", "publish", str(playlist.id)).exit_code, 0
            )
        self.network.assert_not_called()
        self.assertIsNone(playlist.remote_id)

    def test_creation_timeout_is_not_replayed_and_does_not_create_locally(
        self,
    ):
        config.sync.playlist = True
        self.api.failures["POST", "playlist/create-playlist"] = APIError(
            "TEST_PRIVATE_TOKEN"
        )
        result = self.invoke("pl", "create", "Unknown outcome")
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("TEST_PRIVATE", result.output)
        self.assertEqual(self.db.list_playlists(), [])
        self.assertEqual(len(self.writes()), 1)

    def test_create_linked_and_cloud_add_precedes_local_commit(self):
        config.sync.playlist = True
        self.ok("pl", "create", "Created")
        playlist = self.db.get_playlist("Created")
        self.assertTrue(playlist.members_complete)

        def observe(method, route, payload):
            if method == "POST" and route == "playlist/add-works-to-playlist":
                self.assertEqual(playlist.works, [])

        self.api.hook = observe
        self.ok("pl", "add", str(playlist.id), "RJ000123")
        self.assertEqual([work.id for work in playlist.works], [123])
        self.assertEqual(self.api.members[str(playlist.remote_id)], [200123])

    def test_cloud_add_failure_does_not_modify_local_members(self):
        config.sync.playlist = True
        playlist = self.linked()
        self.api.failures["POST", "playlist/add-works-to-playlist"] = APIError(
            "failed"
        )
        self.assertNotEqual(
            self.invoke("pl", "add", str(playlist.id), "RJ000123").exit_code, 0
        )
        self.assertEqual(playlist.works, [])

    def test_cloud_success_local_failure_reports_id_and_keeps_local_members(
        self,
    ):
        config.sync.playlist = True
        playlist = self.linked()
        with patch.object(
            self.db, "commit", side_effect=SQLAlchemyError("TEST_PRIVATE_SQL")
        ):
            result = self.invoke("pl", "add", str(playlist.id), "RJ000123")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(str(playlist.remote_id), result.output)
        self.assertIn("Cloud operation succeeded", result.output)
        self.assertNotIn("TEST_PRIVATE", result.output)
        self.assertEqual(playlist.works, [])
        self.assertEqual(self.api.members[str(playlist.remote_id)], [200123])

    def test_publish_verification_failure_keeps_id_for_recovery(self):
        config.sync.playlist = True
        playlist = self.db.create_playlist("Partial")
        self.db.add_playlist_works(playlist.id, [123])
        self.db.commit()
        self.api.failures["GET", "playlist/get-playlist-works"] = APIError(
            "failed"
        )
        result = self.invoke("pl", "publish", str(playlist.id))
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(str(playlist.remote_id), result.output)
        self.assertFalse(playlist.members_complete)
        self.assertEqual([work.id for work in playlist.works], [123])
        self.assertNotEqual(
            self.invoke("pl", "publish", str(playlist.id)).exit_code, 0
        )
        self.assertEqual(
            len(
                [
                    event
                    for event in self.writes()
                    if event[1] == "playlist/create-playlist"
                ]
            ),
            1,
        )

    def test_link_never_matches_names_or_replaces_local_members(self):
        config.sync.playlist = True
        playlist = self.db.create_playlist("Same")
        self.db.add_playlist_works(playlist.id, [123])
        self.db.commit()
        self.api.playlist("Same", [200123])
        target = self.api.playlist("Different", [100000456])
        self.ok("pl", "link", str(playlist.id), str(target))
        self.assertEqual(playlist.remote_id, target)
        self.assertEqual(playlist.name, "Same")
        self.assertEqual([work.id for work in playlist.works], [123])
        self.assertFalse(playlist.members_complete)
        self.assertEqual(self.writes(), [])

    def test_link_rejects_unowned_and_duplicate_ids(self):
        config.sync.playlist = True
        first = self.linked()
        second = self.db.create_playlist("Second")
        self.db.commit()
        result = self.invoke(
            "pl", "link", str(second.id), str(first.remote_id)
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIsNone(second.remote_id)
        self.api.playlists[str(first.remote_id)]["user_name"] = "other-user"
        self.assertNotEqual(
            self.invoke(
                "pl", "link", str(second.id), str(first.remote_id)
            ).exit_code,
            0,
        )
        self.assertEqual(self.writes(), [])

    def test_playlist_binding_rejects_account_or_service_mismatch(self):
        config.sync.playlist = True
        playlist = self.linked()
        for name in ("remote_user", "remote_service"):
            original = getattr(playlist, name)
            setattr(playlist, name, "other")
            self.db.commit()
            self.assertNotEqual(
                self.invoke(
                    "pl", "add", str(playlist.id), "RJ000123"
                ).exit_code,
                0,
            )
            self.assertEqual(self.writes(), [])
            self.assertEqual(playlist.works, [])
            setattr(playlist, name, original)
            self.db.commit()

    def test_cloud_remove_failure_keeps_local_playlists_and_works(self):
        config.sync.playlist = True
        playlist = self.linked([123])
        self.api.failures["POST", "playlist/delete-playlist"] = APIError(
            "failed"
        )
        self.assertNotEqual(
            self.invoke("pl", "rm", str(playlist.id)).exit_code, 0
        )
        self.assertIs(self.db.get_playlist(playlist.id), playlist)
        self.assertEqual([work.id for work in playlist.works], [123])
        del self.api.failures["POST", "playlist/delete-playlist"]
        self.ok("pl", "rm", str(playlist.id))
        self.assertEqual(self.db.list_playlists(), [])
        self.assertIsNotNone(self.work())

    def test_pull_same_values_does_not_commit_or_push(self):
        config.sync = SyncConfig(star=True, comment=True, progress=True)
        for info in self.infos:
            self.review(
                info["id"],
                userRating=2,
                review_text="Local",
                progress="marked",
            )
        before = self.state()
        with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            self.ok("sync", "pull")
        commit.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.writes(), [])

    def test_noninteractive_pull_skips_conflicts_without_input(self):
        config.sync.star = True
        self.review()
        before = self.state()
        result = self.invoke("sync", "pull", "--no-interactive")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("skipped=3", result.output)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.writes(), [])

    def test_interactive_pull_supports_per_field_and_remaining_choice(self):
        config.sync = SyncConfig(star=True, comment=True, progress=True)
        self.review()
        before = self.state()
        self.ok("sync", "pull", "--interactive", input="cloud\nlocal-all\n")
        after = self.state()
        self.assertEqual(after[0], 4)
        self.assertEqual(after[1:], before[1:])
        self.assertEqual(self.writes(), [])

    def test_adopt_cloud_preserves_private_state_dates_files_and_disabled_fields(
        self,
    ):
        config.sync.comment = True
        self.review(review_text="Cloud current")
        before = self.state()
        self.ok("sync", "pull", "--choice", "cloud")
        after = self.state()
        self.assertEqual(after[1], "Cloud current")
        self.assertEqual((after[0], *after[2:]), (before[0], *before[2:]))
        self.fm.store.assert_not_called()
        self.assertEqual(self.writes(), [])

    def test_missing_review_requires_explicit_choice_to_clear(self):
        config.sync.progress = True
        before = self.state()
        self.assertNotEqual(self.invoke("sync", "pull").exit_code, 0)
        self.assertEqual(self.state(), before)
        self.ok("sync", "pull", "--choice", "cloud")
        self.assertIsNone(self.work().progress)
        self.assertEqual(self.state()[3:], before[3:])

    def test_cloud_only_work_imports_metadata_and_enabled_state_without_download(
        self,
    ):
        config.sync = SyncConfig(comment=True, progress=True)
        info = work_info("RJ000999", 200999)
        self.api.works[200999] = info
        self.review(200999, review_text="New comment", progress="listened")
        self.ok("sync", "pull", "--choice", "cloud")
        work = self.work(999)
        self.assertIsNotNone(work)
        self.assertEqual(
            (work.star, work.comment, work.progress),
            (0, "New comment", "listened"),
        )
        self.assertIsNone(work.last_review)
        self.assertFalse(work.stored)
        self.assertFalse(work.held)
        self.assertEqual(work.details["source_id"], "RJ000999")
        self.fm.store.assert_not_called()
        self.assertEqual(self.writes(), [])

    def test_cloud_playlists_import_once_with_distinct_local_id(self):
        config.sync.playlist = True
        remote_id = self.api.playlist("Imported", [200123, 100000456])
        self.ok("sync", "pull", "--choice", "cloud")
        playlist = self.db.get_playlist("Imported")
        self.assertNotEqual(playlist.id, remote_id)
        self.assertEqual(playlist.remote_id, remote_id)
        self.assertEqual(
            {work.id for work in playlist.works}, {123, 300000456}
        )
        with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            self.ok("sync", "pull")
        commit.assert_not_called()
        self.assertEqual(len(self.db.list_playlists()), 1)
        self.assertEqual(self.writes(), [])

    def test_missing_cloud_playlist_is_not_automatically_deleted(self):
        config.sync.playlist = True
        playlist = self.linked([123])
        unlinked = self.db.create_playlist("Local-only")
        self.db.commit()
        del self.api.playlists[str(playlist.remote_id)]
        result = self.invoke("sync", "pull")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIs(self.db.get_playlist(playlist.id), playlist)
        self.ok("sync", "pull", "--choice", "cloud")
        self.assertEqual(
            [item.id for item in self.db.list_playlists()], [unlinked.id]
        )
        self.assertIsNotNone(self.work())

    def test_pagination_failure_does_not_apply_any_difference(self):
        config.sync = SyncConfig(star=True, playlist=True)
        self.review()
        playlist = self.linked([123])
        self.api.failures["GET", "playlist/get-playlist-works"] = APIError(
            "TEST_PRIVATE_TOKEN"
        )
        before = self.state()
        with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            result = self.invoke("sync", "pull", "--choice", "cloud")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Nothing was applied", result.output)
        self.assertNotIn("TEST_PRIVATE", result.output)
        commit.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual([work.id for work in playlist.works], [123])

    def test_review_pagination_detects_count_changes_and_duplicate_rows(self):
        config.sync.star = True
        for index in range(21):
            info = work_info(f"RJ{1000 + index:06d}", 201000 + index)
            self.api.works[info["id"]] = info
            self.review(info["id"])

        def change_count(method, route, params):
            if method == "GET" and route == "review" and params["page"] == 2:
                self.api.reviews.pop(201020, None)

        self.api.hook = change_count
        before = self.state()
        result = self.invoke("sync", "pull", "--choice", "cloud")
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.db.session.query(ASMR).count(), 3)
        self.api.hook = None
        manager = CloudSync(self.api)
        original = self.api.get_reviews

        async def duplicate_page(page=1, page_size=20, progress=None):
            result = await original(page=page, page_size=page_size)
            if page == 2 and result["works"]:
                result["works"][0] = {
                    **self.api.works[201000],
                    **self.api.reviews[201000],
                }
            return result

        self.api.get_reviews = duplicate_page
        info = work_info("RJ001020", 201020)
        self.api.works[201020] = info
        self.review(201020)
        with self.assertRaisesRegex(SyncError, "Duplicate"):
            manager.run(manager.snapshot(True, False, {123}))

    def test_pull_local_failure_reports_failed_and_keeps_other_applied_records(
        self,
    ):
        config.sync.star = True
        self.review()
        original_commit = self.db.commit
        calls = 0

        def fail_first():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise SQLAlchemyError("TEST_PRIVATE_SQL")
            original_commit()

        with patch.object(self.db, "commit", side_effect=fail_first):
            result = self.invoke("sync", "pull", "--choice", "cloud")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("failed=1", result.output)
        self.assertNotIn("TEST_PRIVATE", result.output)
        self.assertEqual(self.work().star, 2)
        self.assertEqual(self.work(300000456).star, 0)
        self.assertEqual(self.writes(), [])

    def test_publish_local_commit_failure_reports_created_id_without_retry(
        self,
    ):
        config.sync.playlist = True
        playlist = self.db.create_playlist("Local commit fails")
        self.db.commit()
        with patch.object(
            self.db, "commit", side_effect=SQLAlchemyError("TEST_PRIVATE_SQL")
        ):
            result = self.invoke("pl", "publish", str(playlist.id))
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Cloud operation succeeded", result.output)
        self.assertNotIn("TEST_PRIVATE", result.output)
        remote_id = next(iter(self.api.playlists))
        self.assertIn(remote_id, result.output)
        self.assertIsNone(playlist.remote_id)
        self.assertEqual(len(self.writes()), 1)

    def test_bad_creation_id_never_binds_or_retries(self):
        config.sync.playlist = True
        original_post = self.api.post

        async def bad_id(route, data=None):
            response = await original_post(route, data)
            if route == "playlist/create-playlist":
                return {**response, "id": "TEST_PRIVATE_INVALID_ID"}
            return response

        self.api.post = bad_id
        result = self.invoke("pl", "create", "Missing ID")
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("TEST_PRIVATE", result.output)
        self.assertEqual(self.db.list_playlists(), [])
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(len(self.api.playlists), 1)

    def test_partial_member_publication_keeps_binding_and_does_not_claim_complete(
        self,
    ):
        config.sync.playlist = True
        playlist = self.db.create_playlist("Partial members")
        self.db.add_playlist_works(playlist.id, [123, 300000456])
        self.db.commit()

        def lose_member(method, route, payload):
            if method == "GET" and route == "playlist/get-playlist-metadata":
                self.api.members[payload["id"]] = [200123]

        self.api.hook = lose_member
        result = self.invoke("pl", "publish", str(playlist.id))
        self.assertNotEqual(result.exit_code, 0)
        self.assertIsNotNone(playlist.remote_id)
        self.assertFalse(playlist.members_complete)
        self.assertEqual(
            {work.id for work in playlist.works}, {123, 300000456}
        )
        self.assertEqual(len(self.writes()), 1)

    def test_partial_cloud_deletion_keeps_all_local_lists_until_pull(self):
        config.sync.playlist = True
        first, second = (
            self.linked([123], "First"),
            self.linked([300000456], "Second"),
        )
        original = self.api.post

        async def fail_second(route, data=None):
            if route == "playlist/delete-playlist" and data["id"] == str(
                second.remote_id
            ):
                raise APIError("TEST_PRIVATE_TOKEN")
            return await original(route, data)

        self.api.post = fail_second
        result = self.invoke("pl", "rm", str(first.id), str(second.id))
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("TEST_PRIVATE", result.output)
        self.assertEqual(len(self.db.list_playlists()), 2)
        self.assertNotIn(str(first.remote_id), self.api.playlists)
        self.assertIn(str(second.remote_id), self.api.playlists)
        self.ok("sync", "pull", "--choice", "cloud")
        self.assertEqual(
            [item.id for item in self.db.list_playlists()], [second.id]
        )

    def test_pull_cloud_all_applies_remaining_conflicts_without_more_prompts(
        self,
    ):
        config.sync = SyncConfig(star=True, comment=True)
        self.review()
        result = self.ok("sync", "pull", "--interactive", input="cloud-all\n")
        self.assertEqual(result.output.count("Choose ("), 1)
        self.assertEqual((self.work().star, self.work().comment), (4, "Cloud"))
        self.assertEqual(self.work(300000456).star, 0)
        self.assertEqual(self.writes(), [])

    def test_keep_local_choice_is_successful_and_never_reverse_pushes(self):
        config.sync.star = True
        self.review()
        before = self.state()
        self.ok("sync", "pull", "--choice", "local")
        self.assertEqual(self.state(), before)
        self.assertEqual(self.writes(), [])

    def test_incomplete_legacy_members_are_reconciled_only_on_adoption(self):
        config.sync.playlist = True
        playlist = self.linked([123])
        playlist.members_complete = False
        self.api.members[str(playlist.remote_id)] = [100000456]
        self.db.commit()
        self.ok("sync", "pull", "--choice", "local")
        self.assertFalse(playlist.members_complete)
        self.assertEqual([work.id for work in playlist.works], [123])
        self.ok("sync", "pull", "--choice", "cloud")
        self.assertTrue(playlist.members_complete)
        self.assertEqual([work.id for work in playlist.works], [300000456])

    def test_playlist_only_pull_imports_new_metadata_without_review_or_file_changes(
        self,
    ):
        config.sync.playlist = True
        info = work_info("BJ000999", 200000999)
        self.api.works[info["id"]] = info
        self.review(info["id"])
        self.api.playlist("Cloud only", [info["id"]])
        self.ok("sync", "pull", "--choice", "cloud")
        work = self.work(400000999)
        self.assertEqual(
            (work.star, work.comment, work.progress), (0, "", None)
        )
        self.assertIsNone(work.last_review)
        self.assertFalse(work.stored)
        self.assertFalse(work.held)
        self.fm.store.assert_not_called()
        self.assertFalse(
            any(event[:2] == ("GET", "review") for event in self.api.events)
        )
        self.assertEqual(self.writes(), [])

    def test_first_page_recheck_prevents_stale_missing_data(self):
        config.sync.star = True
        self.review()
        reads = 0

        def change(method, route, payload):
            nonlocal reads
            if method == "GET" and route == "review":
                reads += 1
                if reads == 2:
                    self.api.reviews.clear()

        self.api.hook = change
        before = self.state()
        self.assertNotEqual(
            self.invoke("sync", "pull", "--choice", "cloud").exit_code, 0
        )
        self.assertEqual(self.state(), before)

    def test_malformed_and_incomplete_member_pages_never_clear_local_members(
        self,
    ):
        config.sync.playlist = True
        playlist = self.linked([123])
        original = self.api.get
        for malformed in (
            None,
            {},
            {"works": [], "pagination": None},
            {
                "works": [],
                "pagination": {"page": 1, "pageSize": 20, "totalCount": 1},
            },
            {
                "works": [None],
                "pagination": {"page": 1, "pageSize": 20, "totalCount": 1},
            },
        ):

            async def invalid(route, params=None, value=malformed):
                if route == "playlist/get-playlist-works":
                    return value
                return await original(route, params)

            self.api.get = invalid
            self.assertNotEqual(
                self.invoke("sync", "pull", "--choice", "cloud").exit_code, 0
            )
            self.assertEqual([work.id for work in playlist.works], [123])

    def test_unknown_remote_work_mapping_and_missing_review_keys_block_pull(
        self,
    ):
        config.sync.star = True
        self.review()
        before = self.state()
        self.api.works[200123]["source_id"] = "RJ300000123"
        self.assertNotEqual(
            self.invoke("sync", "pull", "--choice", "cloud").exit_code, 0
        )
        self.assertEqual(self.state(), before)
        self.api.works[200123]["source_id"] = "RJ000123"
        del self.api.reviews[200123]["review_text"]
        self.assertNotEqual(
            self.invoke("sync", "pull", "--choice", "cloud").exit_code, 0
        )
        self.assertEqual(self.state(), before)

    def test_invalid_service_address_never_opens_a_session(self):
        for address in (
            "https://user:TEST_PRIVATE_TOKEN@test.example/api/",
            "https://test.example/api/?token=TEST_PRIVATE_TOKEN",
            "https://test.example/other/",
            "file:///api/",
            "https://[TEST_PRIVATE_TOKEN/api/",
        ):
            self.api.base_api_url = address
            with self.assertRaises(SyncError) as error:
                CloudSync(self.api)
            self.assertNotIn("TEST_PRIVATE", str(error.exception))
        self.assertEqual(self.api.events, [])

    def test_complete_multiple_pages_import_each_work_once(self):
        config.sync.star = True
        for index in range(21):
            info = work_info(f"RJ{1000 + index:06d}", 201000 + index)
            self.api.works[info["id"]] = info
            self.review(info["id"])
        self.ok("sync", "pull", "--choice", "cloud")
        self.assertEqual(self.db.session.query(ASMR).count(), 24)
        self.assertEqual(self.work(1020).star, 4)
        self.assertIsNone(self.work(1020).last_review)
        self.assertEqual(self.writes(), [])

    def test_playlist_change_during_member_collection_blocks_all_application(
        self,
    ):
        config.sync.playlist = True
        playlist = self.linked([123])
        reads = 0

        def change(method, route, params):
            nonlocal reads
            if method == "GET" and route == "playlist/get-playlist-metadata":
                reads += 1
                if reads == 2:
                    self.api.playlists[params["id"]]["description"] = (
                        "Changed during pull"
                    )

        self.api.hook = change
        result = self.invoke("sync", "pull", "--choice", "cloud")
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(playlist.description, "")
        self.assertEqual([work.id for work in playlist.works], [123])

    def test_conflicting_remote_ids_for_the_same_source_block_pull(self):
        config.sync = SyncConfig(star=True, playlist=True)
        self.review()
        self.api.works[200999] = work_info("RJ000123", 200999)
        self.api.playlist("Conflicting mapping", [200999])
        before = self.state()
        result = self.invoke("sync", "pull", "--choice", "cloud")
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.db.list_playlists(), [])

    def test_unknown_review_fields_and_other_owner_are_not_absence(self):
        config.sync.star = True
        self.review(progress="unknown")
        before = self.state()
        self.assertNotEqual(
            self.invoke("sync", "pull", "--choice", "cloud").exit_code, 0
        )
        self.assertEqual(self.state(), before)
        self.review(user_name="other-user")
        self.assertNotEqual(
            self.invoke("sync", "pull", "--choice", "cloud").exit_code, 0
        )
        self.assertEqual(self.state(), before)

    def test_pull_mismatched_binding_cannot_create_duplicate_association(self):
        config.sync.playlist = True
        playlist = self.linked([123])
        playlist.remote_user = "other-user"
        self.db.commit()
        before = (playlist.name, [work.id for work in playlist.works])
        self.assertNotEqual(
            self.invoke("sync", "pull", "--choice", "cloud").exit_code, 0
        )
        self.assertEqual(
            (playlist.name, [work.id for work in playlist.works]), before
        )
        self.assertEqual(self.db.session.query(Playlist).count(), 1)
