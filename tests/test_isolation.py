import tests

from pathlib import Path
from unittest import TestCase

from asmrmanager.cli.core import PREVIOUS_RJ_PATH, get_prev_source, save_source
from asmrmanager.config import config
from asmrmanager.filemanager.appdirs_ import (
    CACHE_PATH,
    CONFIG_PATH,
    DATA_PATH,
    LOG_PATH,
)


class TestIsolation(TestCase):
    def test_application_paths_are_temporary(self):
        root = Path(tests._environment.name)
        for path in (
            CONFIG_PATH,
            DATA_PATH,
            CACHE_PATH,
            LOG_PATH,
            PREVIOUS_RJ_PATH,
            Path(config.download_path),
            Path(config.storage_path),
            Path(config.view_path),
        ):
            with self.subTest(path=path):
                self.assertTrue(path.is_relative_to(root), path)

    def test_previous_source_is_written_only_to_temporary_data(self):
        self.assertTrue(PREVIOUS_RJ_PATH.is_relative_to(Path(tests._environment.name)))
        previous = PREVIOUS_RJ_PATH.read_bytes() if PREVIOUS_RJ_PATH.exists() else None
        try:
            save_source("RJ000123")
            self.assertEqual(PREVIOUS_RJ_PATH.read_text(encoding="utf-8"), "RJ000123")
            self.assertEqual(get_prev_source(), "RJ000123")
        finally:
            if previous is None:
                PREVIOUS_RJ_PATH.unlink(missing_ok=True)
            else:
                PREVIOUS_RJ_PATH.write_bytes(previous)
            get_prev_source.cache_clear()
