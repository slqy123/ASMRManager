import sys
from datetime import UTC, date, datetime
from unittest import TestCase
from unittest.mock import patch

from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from asmrmanager.cli.main import main
from asmrmanager.config import SyncConfig, config
from asmrmanager.database.manage import DataBaseManager
from asmrmanager.logger import logger
from asmrmanager.spider.asmrapi import APIError
from tests.fake_cloud import FakeCloud
from tests.test_local_database import work_info


class ReviewSyncBoundaryTest(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.db = DataBaseManager(self.engine)
        self.addCleanup(self.db.session.close)
        self.db.add_info(work_info())
        self.initial_date = date(2001, 2, 3)
        self.today = datetime.now(UTC).astimezone().date()
        self.reset_review()
        self.enterContext(patch.object(config, "sync", SyncConfig()))
        self.enterContext(
            patch("asmrmanager.cli.core.create_database", return_value=self.db)
        )
        self.enterContext(
            patch(
                "asmrmanager.cli.review.create_database", return_value=self.db
            )
        )
        self.enterContext(patch("asmrmanager.cli.core.save_source"))
        self.fm = self.enterContext(patch("asmrmanager.cli.review.fm"))
        self.fm.could_store.return_value = False
        self.api = FakeCloud([work_info()])
        self.api.failures["PUT", "review"] = APIError(
            "TEST_PRIVATE_NETWORK_ERROR"
        )
        self.network = self.enterContext(
            patch(
                "asmrmanager.cli.core.create_api_client", return_value=self.api
            )
        )
        self.runner = CliRunner()

    def reset_review(self):
        work = self.db.resolve_local_work("RJ000123")
        work.star = 2
        work.comment = "Before"
        work.progress = "marked"
        work.last_review = self.initial_date
        work.notes = "TEST_PRIVATE_NOTE"
        work.held = True
        work.stored = False
        self.db.commit()

    def reload_work(self):
        self.db.session.expire_all()
        return self.db.resolve_local_work("RJ000123")

    def invoke(self, *options):
        return self.runner.invoke(main, ["review", "RJ000123", *options])

    def assert_sync_failure(self, result, fields):
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Local review changes were saved", result.output)
        self.assertIn("cloud synchronization failed", result.output)
        self.assertIn("asmr sync push", result.output)
        self.assertNotIn("synchronized.", result.output)
        requests = [
            event
            for event in self.api.events
            if event[:2] == ("PUT", "review")
        ]
        self.assertTrue(requests)
        mapping = {
            "star": "rating",
            "comment": "review_text",
            "progress": "progress",
        }
        self.assertEqual(
            set(requests[-1][2]["data"]) - {"work_id"},
            {mapping[name] for name in fields},
        )
        self.assertNotIn("TEST_PRIVATE", result.output)

    def assert_initial_review(self):
        work = self.reload_work()
        self.assertEqual(
            (work.star, work.comment, work.progress), (2, "Before", "marked")
        )
        self.assertEqual(work.last_review, self.initial_date)
        self.assertEqual(work.notes, "TEST_PRIVATE_NOTE")
        self.assertTrue(work.held)
        self.assertFalse(work.stored)

    def test_reports_only_submitted_enabled_fields_after_saving_all_changes(
        self,
    ):
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
                self.reset_review()
                config.sync = SyncConfig(**{field: True for field in fields})
                result = self.invoke(
                    "--star",
                    "5",
                    "--comment",
                    "TEST_PRIVATE_COMMENT",
                    "--progress",
                    "listening",
                )
                self.assert_sync_failure(result, fields)
                work = self.reload_work()
                self.assertEqual(
                    (work.star, work.comment, work.progress),
                    (5, "TEST_PRIVATE_COMMENT", "listening"),
                )
                self.assertEqual(work.last_review, self.today)
                self.assertEqual(work.notes, "TEST_PRIVATE_NOTE")
                self.assertTrue(work.held)
                self.assertFalse(work.stored)

    def test_enabled_flags_for_omitted_fields_do_not_fail_local_changes(self):
        for field, options, expected in (
            ("star", ("--star", "5"), (5, "Before", "marked")),
            ("comment", ("--comment", "Current"), (2, "Current", "marked")),
            (
                "progress",
                ("--progress", "listening"),
                (2, "Before", "listening"),
            ),
        ):
            with self.subTest(field=field):
                self.reset_review()
                config.sync = SyncConfig(
                    **{
                        name: name != field
                        for name in ("star", "comment", "progress", "playlist")
                    }
                )
                result = self.invoke(*options)
                self.assertEqual(result.exit_code, 0, result.output)
                work = self.reload_work()
                self.assertEqual(
                    (work.star, work.comment, work.progress), expected
                )
                self.assertEqual(
                    work.last_review,
                    self.initial_date if field == "progress" else self.today,
                )

    def test_explicit_clears_are_submitted_fields_and_remain_saved(self):
        for field, options, expected in (
            ("star", ("--star", "0"), (0, "Before", "marked")),
            ("comment", ("--comment", ""), (2, "", "marked")),
            ("progress", ("--clear-progress",), (2, "Before", None)),
        ):
            with self.subTest(field=field):
                self.reset_review()
                config.sync = SyncConfig(**{field: True})
                result = self.invoke(*options)
                self.assert_sync_failure(result, (field,))
                work = self.reload_work()
                self.assertEqual(
                    (work.star, work.comment, work.progress), expected
                )
                self.assertEqual(
                    work.last_review,
                    self.initial_date if field == "progress" else self.today,
                )

    def test_progress_sync_failure_keeps_date_and_files_untouched(self):
        config.sync = SyncConfig(progress=True)
        result = self.invoke("--progress", "listened")
        self.assert_sync_failure(result, ("progress",))
        work = self.reload_work()
        self.assertEqual(work.progress, "listened")
        self.assertEqual(work.last_review, self.initial_date)
        self.assertEqual((work.star, work.comment), (2, "Before"))
        self.assertEqual(work.notes, "TEST_PRIVATE_NOTE")
        self.assertTrue(work.held)
        self.assertFalse(work.stored)
        self.fm.could_store.assert_not_called()
        self.fm.get_location.assert_not_called()
        self.fm.store.assert_not_called()

    def test_sync_failure_occurs_after_commit_and_does_not_roll_back_storage_state(
        self,
    ):
        config.sync = SyncConfig(star=True)
        self.fm.could_store.return_value = True
        self.fm.get_location.side_effect = ["download", "storage"]
        with (
            patch.object(self.db, "commit", wraps=self.db.commit) as commit,
            patch.object(
                self.db.session, "rollback", wraps=self.db.session.rollback
            ) as rollback,
        ):
            result = self.invoke("--star", "5")
        self.assert_sync_failure(result, ("star",))
        commit.assert_called_once_with()
        rollback.assert_not_called()
        self.fm.store.assert_called_once_with(123)
        work = self.reload_work()
        self.assertEqual(work.star, 5)
        self.assertEqual(work.last_review, self.today)
        self.assertTrue(work.stored)
        self.assertEqual(work.notes, "TEST_PRIVATE_NOTE")
        self.assertTrue(work.held)

    def test_local_commit_failure_rolls_back_without_claiming_saved_or_exposing_sql(
        self,
    ):
        config.sync = SyncConfig(star=True, comment=True)
        error = IntegrityError(
            "UPDATE asmr SET comment = :comment",
            {"comment": "TEST_PRIVATE_COMMENT"},
            RuntimeError("TEST_PRIVATE_DATABASE_ERROR"),
        )
        with (
            patch.object(self.db, "commit", side_effect=error),
            patch.object(
                self.db.session, "rollback", wraps=self.db.session.rollback
            ) as rollback,
            self.assertLogs(logger, level="DEBUG") as logs,
        ):
            result = self.invoke(
                "--star", "5", "--comment", "TEST_PRIVATE_COMMENT"
            )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Could not save local review changes", result.output)
        self.assertNotIn("changes were saved", result.output)
        self.assertNotIn("cloud synchronization", result.output)
        self.assertNotIn(
            "TEST_PRIVATE", result.output + "\n".join(logs.output)
        )
        rollback.assert_called_once_with()
        self.assert_initial_review()
        self.fm.store.assert_not_called()

    def test_invalid_review_does_not_report_saved_or_move_files(self):
        config.sync = SyncConfig(star=True, comment=True, progress=True)
        result = self.invoke(
            "--star",
            "5",
            "--comment",
            "TEST_PRIVATE_COMMENT",
            "--progress",
            "listening",
            "--clear-progress",
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn(
            "Cannot set and clear listening status together", result.output
        )
        self.assertNotIn("changes were saved", result.output)
        self.assertNotIn("cloud synchronization", result.output)
        self.assert_initial_review()
        self.fm.could_store.assert_not_called()
        self.fm.store.assert_not_called()

    def test_no_submitted_fields_does_not_claim_saved_or_synchronized(self):
        config.sync = SyncConfig(star=True, comment=True, progress=True)
        result = self.invoke()
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(
            "Specify a rating, comment or listening status", result.output
        )
        self.assertNotIn("changes were saved", result.output)
        self.assertNotIn("cloud synchronization", result.output)
        self.assert_initial_review()
        self.fm.store.assert_not_called()

    def test_cli_logs_command_name_without_private_arguments(self):
        config.sync = SyncConfig(comment=True)
        arguments = ["review", "RJ000123", "--comment", "TEST_PRIVATE_COMMENT"]
        with (
            patch.object(sys, "argv", ["asmr", *arguments]),
            self.assertLogs(logger, level="DEBUG") as logs,
        ):
            result = self.runner.invoke(main, arguments)
        self.assert_sync_failure(result, ("comment",))
        self.assertIn("Running command: review", "\n".join(logs.output))
        self.assertNotIn("TEST_PRIVATE", "\n".join(logs.output))
        self.assertNotIn("--comment", "\n".join(logs.output))

    def test_root_help_and_version_remain_available(self):
        for option in ("--help", "--version"):
            with self.subTest(option=option):
                result = self.runner.invoke(main, [option])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn(
                    "review" if option == "--help" else "ASMRManager",
                    result.output,
                )
                self.fm.store.assert_not_called()
