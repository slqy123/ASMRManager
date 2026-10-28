import tests

import runpy
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import toml
from click.testing import CliRunner
from sqlalchemy import create_engine

import asmrmanager.config as configuration
from asmrmanager.cli.review import review
from asmrmanager.config import SyncConfig
from asmrmanager.database.manage import DataBaseManager
from tests.test_local_database import work_info


class SyncConfigTest(TestCase):
    def setUp(self):
        self.example = toml.load(
            Path(__file__).resolve().parents[1]
            / "asmrmanager/filemanager/resources/config.example.toml"
        )

    def load(self, data):
        with (
            patch("toml.load", return_value=data),
            patch(
                "asmrmanager.cli.core.create_api_client",
                side_effect=AssertionError(
                    "Configuration must not create an API client"
                ),
            ) as network,
        ):
            loaded = runpy.run_path(configuration.__file__)["config"]
            network.assert_not_called()
        return loaded

    def test_defaults_are_all_disabled(self):
        self.assertEqual(
            asdict(SyncConfig()),
            {
                "star": False,
                "comment": False,
                "progress": False,
                "playlist": False,
            },
        )

    def test_legacy_config_without_sync_section_loads_with_disabled_defaults(
        self,
    ):
        data = deepcopy(self.example)
        del data["sync"]
        loaded = self.load(data)
        self.assertEqual(asdict(loaded.sync), asdict(SyncConfig()))
        self.assertEqual(loaded.playlist_aliases, data["playlist_aliases"])

    def test_each_sync_field_can_be_enabled_independently_without_network(
        self,
    ):
        for name in asdict(SyncConfig()):
            with self.subTest(name=name):
                data = deepcopy(self.example)
                data["sync"] = {name: True}
                loaded = self.load(data)
                self.assertEqual(
                    asdict(loaded.sync),
                    {field: field == name for field in asdict(SyncConfig())},
                )

    def test_rejects_non_boolean_values(self):
        for name in asdict(SyncConfig()):
            for value in ("false", "true", 0, 1, None):
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaisesRegex(ValueError, f"sync.{name}"),
                ):
                    SyncConfig(**{name: value})

    def test_loading_invalid_sync_section_fails(self):
        data = deepcopy(self.example)
        data["sync"]["playlist"] = "false"
        with self.assertRaisesRegex(
            ValueError, "sync.playlist must be a boolean"
        ):
            self.load(data)

    def test_debug_logs_do_not_include_configuration_values(self):
        data = deepcopy(self.example)
        data["username"] = "TEST_PRIVATE_USERNAME"
        data["password"] = "TEST_PRIVATE_PASSWORD"
        data["proxy"] = "http://test:TEST_PRIVATE_PROXY@localhost:8080"
        data["aria2_config"]["secret"] = "TEST_PRIVATE_RPC_SECRET"
        with self.assertLogs(configuration.logger, level="DEBUG") as logs:
            loaded = self.load(data)
        self.assertEqual(loaded.username, data["username"])
        self.assertEqual(loaded.password, data["password"])
        self.assertEqual(loaded.proxy, data["proxy"])
        self.assertEqual(
            loaded.aria2_config.secret, data["aria2_config"]["secret"]
        )
        self.assertIn("Config loaded", "\n".join(logs.output))
        self.assertNotIn("TEST_PRIVATE", "\n".join(logs.output))

    def test_disabled_sync_keeps_review_offline_and_progress_side_effect_free(
        self,
    ):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        db = DataBaseManager(engine)
        self.addCleanup(db.session.close)
        db.add_info(work_info())
        db.add_info(work_info("VJ000456", 100000456))
        db.add_info(work_info("BJ000789", 200000789))
        db.session.commit()
        with (
            patch.object(configuration.config, "sync", SyncConfig()),
            patch("asmrmanager.cli.core.create_database", return_value=db),
            patch("asmrmanager.cli.review.create_database", return_value=db),
            patch("asmrmanager.cli.review.fm") as fm,
            patch("asmrmanager.cli.core.save_source"),
            patch(
                "asmrmanager.cli.core.create_api_client",
                side_effect=AssertionError("Review must remain offline"),
            ) as network,
        ):
            fm.could_store.return_value = False
            runner = CliRunner()
            result = runner.invoke(
                review, ["RJ000123", "--star", "5", "--comment", "Current"]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            work = db.resolve_local_work("RJ000123")
            self.assertEqual((work.star, work.comment), (5, "Current"))
            last_review = work.last_review
            for options, expected in (
                (["--progress", "listening"], "listening"),
                (["--clear-progress"], None),
            ):
                result = runner.invoke(review, ["RJ000123", *options])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(work.progress, expected)
                self.assertEqual(work.last_review, last_review)
            for source, expected in (
                ("200123", 123),
                ("100000456", 300000456),
                ("200000789", 400000789),
                ("VJ000456", 300000456),
                ("BJ000789", 400000789),
            ):
                result = runner.invoke(
                    review, [source, "--progress", "listened"]
                )
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(
                    db.resolve_local_work(str(expected)).progress, "listened"
                )
            for source in ("100000999", "RJ200123", "RJ000999"):
                result = runner.invoke(
                    review, [source, "--progress", "listening"]
                )
                self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(work.progress, "listened")
            self.assertEqual(work.last_review, last_review)
            fm.store.assert_not_called()
            network.assert_not_called()

    def test_example_has_disabled_sync_defaults(self):
        self.assertEqual(self.example["sync"], asdict(SyncConfig()))
        self.assertEqual(
            asdict(self.load(self.example).sync), asdict(SyncConfig())
        )
