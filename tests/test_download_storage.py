import tests

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch

from click.testing import CliRunner
from sqlalchemy import create_engine

from asmrmanager.cli.core import create_downloader_and_database
from asmrmanager.cli.file import diff, recover, verify_voices
from asmrmanager.config import Filter, config
from asmrmanager.database.database import ASMR
from asmrmanager.database.manage import DataBaseManager
from asmrmanager.spider.downloader import DownloadError

from tests.test_local_database import recovery, work_info


class DownloadStorageTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'data.db'}")
        self.addCleanup(self.engine.dispose)
        self.db = DataBaseManager(self.engine)
        self.addCleanup(self.db.session.close)
        self.api = SimpleNamespace(
            get_voice_info=AsyncMock(return_value=work_info()),
            get_voice_tracks=AsyncMock(
                return_value=[
                    {
                        "type": "audio",
                        "title": "track.mp3",
                        "hash": "folder/100",
                        "mediaDownloadUrl": "https://example.com/audio",
                    }
                ]
            ),
        )
        self.fm = SimpleNamespace(
            download_path=self.root / "download",
            get_path=lambda *_args, **_kwargs: (
                self.root / "download" / "RJ000123"
            ),
        )
        self.addCleanup(patch.stopall)
        patch("asmrmanager.spider.downloader.fm", self.fm).start()
        patch.dict(
            "sys.modules",
            {
                "asmrmanager.spider.utils.aria2_downloader": SimpleNamespace(
                    Aria2Downloader=Mock()
                )
            },
        ).start()
        patch(
            "asmrmanager.cli.core.create_database", return_value=self.db
        ).start()
        patch(
            "asmrmanager.cli.core.create_api_client", return_value=self.api
        ).start()
        patch.object(config, "download_method", "aria2").start()
        patch.object(
            config, "filename_filters", [Filter(regex=r"\.wav$")]
        ).start()

    def downloader(self):
        manager, _ = create_downloader_and_database()
        return manager.downloader

    async def test_download_persists_details_and_recovery_without_json_files(
        self,
    ):
        downloader = self.downloader()
        downloader.create_dir_and_download = AsyncMock()
        await downloader.download(200123)
        self.assertEqual(self.db.session.get(ASMR, 123).details, work_info())
        records = self.db.load_recovery(123)
        self.assertEqual(records, [recovery("track.mp3")])
        self.assertEqual(list(self.fm.download_path.rglob("*.json")), [])
        self.assertEqual(list(self.fm.download_path.rglob(".recover")), [])
        downloader.create_dir_and_download.assert_awaited_once()

    async def test_submission_failure_keeps_committed_recovery(self):
        downloader = self.downloader()
        downloader.create_dir_and_download = AsyncMock(
            side_effect=DownloadError("submission failed")
        )
        with self.assertRaises(DownloadError):
            await downloader.download(200123)
        independent = DataBaseManager(self.engine)
        self.addCleanup(independent.session.close)
        self.assertEqual(
            independent.load_recovery(123), [recovery("track.mp3")]
        )
        self.assertEqual(
            independent.session.get(ASMR, 123).details, work_info()
        )

    async def test_update_refreshes_database_and_replaces_recovery(self):
        downloader = self.downloader()
        self.db.add_info(work_info())
        self.db.update_review(123, 5, "Keep comment", progress="listening")
        self.db.save_recovery(123, [recovery("outdated.mp3")])
        self.db.session.commit()
        self.api.get_voice_info.return_value = {
            **work_info(),
            "title": "Updated",
        }
        await downloader.update(200123)
        work = self.db.session.get(ASMR, 123)
        self.assertEqual(work.title, "Updated")
        self.assertEqual(work.comment, "Keep comment")
        self.assertEqual(work.progress, "listening")
        self.assertEqual(self.db.load_recovery(123), [recovery("track.mp3")])
        self.api.get_voice_info.assert_awaited_once_with(200123, refresh=True)
        self.assertEqual(list(self.fm.download_path.rglob("*.json")), [])
        self.assertEqual(list(self.fm.download_path.rglob(".recover")), [])

    async def test_update_without_local_directory_persists_metadata(self):
        self.fm.get_path = Mock(return_value=None)
        downloader = self.downloader()
        await downloader.update(200123)
        self.assertEqual(self.db.session.get(ASMR, 123).details, work_info())
        self.assertEqual(self.db.load_recovery(123), [recovery("track.mp3")])
        self.assertFalse(self.fm.download_path.exists())
        self.fm.get_path.assert_called_once_with(123, prefer="download")

    async def test_update_track_failure_keeps_details_without_directory(self):
        self.fm.get_path = Mock(return_value=None)
        self.api.get_voice_tracks.return_value = None
        with self.assertRaises(DownloadError):
            await self.downloader().update(200123)
        independent = DataBaseManager(self.engine)
        self.addCleanup(independent.session.close)
        self.assertEqual(
            independent.session.get(ASMR, 123).details, work_info()
        )
        self.assertIsNone(independent.load_recovery(123))
        self.assertFalse(self.fm.download_path.exists())

    async def test_track_failure_keeps_committed_details(self):
        self.api.get_voice_tracks.return_value = None
        with self.assertRaises(DownloadError):
            await self.downloader().download(200123)
        independent = DataBaseManager(self.engine)
        self.addCleanup(independent.session.close)
        self.assertEqual(
            independent.session.get(ASMR, 123).details, work_info()
        )
        self.assertIsNone(independent.load_recovery(123))


class RecoveryCommandsTest(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'data.db'}")
        self.addCleanup(self.engine.dispose)
        self.db = DataBaseManager(self.engine)
        self.addCleanup(self.db.session.close)
        self.db.add_info(work_info())
        self.db.session.commit()
        self.fm = Mock(
            download_path=self.root, storage_path=self.root / "storage"
        )
        self.fm.get_all_files.return_value = set()
        self.fm.check_exists.return_value = (True, False)
        self.addCleanup(patch.stopall)
        patch(
            "asmrmanager.cli.file.create_database", return_value=self.db
        ).start()
        patch("asmrmanager.cli.file.fm", self.fm).start()

    def test_recover_skips_existing_path_objects(self):
        self.db.save_recovery(
            123, [recovery("existing.mp3"), recovery("missing.mp3")]
        )
        self.db.session.commit()
        self.fm.get_all_files.return_value = {Path("existing.mp3")}
        manager = Mock()
        with patch(
            "asmrmanager.cli.core.create_downloader_and_database",
            return_value=(manager, self.db),
        ):
            result = CliRunner().invoke(recover, ["RJ000123"])
        self.assertEqual(result.exit_code, 0, result.output)
        manager.downloader.process_download.assert_called_once_with(
            "https://example.com/audio", self.root / "RJ000123", "missing.mp3"
        )

    def test_missing_recovery_is_an_error(self):
        result = CliRunner().invoke(recover, ["RJ000123"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("No recovery records", result.output)

    def test_diff_uses_database_without_recovery_file(self):
        self.db.save_recovery(123, [recovery()])
        self.db.session.commit()
        result = CliRunner().invoke(diff, ["RJ000123"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.fm.get_all_files.assert_called_once_with(123)

    def test_offline_verify_uses_database_without_recovery_file(self):
        self.db.save_recovery(123, [recovery()])
        self.db.session.commit()
        self.fm.get_all_files.return_value = {Path("audio/track.mp3")}
        self.assertTrue(verify_voices(123, offline=True))

    def test_online_verify_reports_missing_legacy_file_id(self):
        record = recovery()
        del record["fileId"]
        self.db.save_recovery(123, [record])
        self.db.session.commit()
        self.fm.get_all_files.return_value = {Path("audio/track.mp3")}
        with patch("asmrmanager.cli.file.create_general_api") as api:
            self.assertFalse(verify_voices(123, offline=False))
            api.assert_not_called()

    def test_empty_recovery_is_not_missing(self):
        self.db.save_recovery(123, [])
        self.db.session.commit()
        self.assertTrue(verify_voices(123, offline=True))
