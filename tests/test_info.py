import tests

from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from rich.console import Console
from sqlalchemy import create_engine

from asmrmanager.cli.info import print_asmr_info
from asmrmanager.database.database import ASMR
from asmrmanager.database.manage import DataBaseManager

from tests.test_local_database import work_info


class InfoLanguageEditionsTest(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        self.db = DataBaseManager(self.engine)
        self.addCleanup(self.db.session.close)
        self.db.add_info(work_info())
        self.db.session.commit()
        self.work = self.db.session.get(ASMR, 123)

    def render(self):
        output = StringIO()
        console = Console(file=output, width=120, force_terminal=False)
        with (
            patch("asmrmanager.cli.info.support_image", return_value=False),
            patch("rich.console.Console", return_value=console),
            patch("asmrmanager.cli.info.create_general_api") as api,
        ):
            print_asmr_info(self.work)
        api.assert_not_called()
        return output.getvalue()

    def test_displays_language_editions_from_details(self):
        self.work.details = {
            "language_editions": [
                {"lang": "JPN", "label": "日本語", "workno": "RJ01658474"},
                {"lang": "CHI_HANS", "label": "簡体中文", "workno": "RJ01681252"},
                {"lang": "CHI_HANT", "label": "繁体中文", "workno": "RJ01681250"},
            ]
        }
        output = self.render()
        self.assertIn("language editions", output)
        for label, workno in (
            ("日本語", "RJ01658474"),
            ("簡体中文", "RJ01681252"),
            ("繁体中文", "RJ01681250"),
        ):
            self.assertIn(label, output)
            self.assertIn(workno, output)

    def test_omits_section_for_missing_or_empty_editions(self):
        for details in (None, {}, {"language_editions": None}, {"language_editions": []}):
            with self.subTest(details=details):
                self.work.details = details
                self.assertNotIn("language editions", self.render())

    def test_uses_language_code_and_skips_incomplete_entries(self):
        self.work.details = {
            "language_editions": [None, {}, {"lang": "ENG", "workno": "RJ000456"}]
        }
        output = self.render()
        self.assertIn("ENG: RJ000456", output)
