from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NamedTuple, Self

from aiohttp import ClientConnectionError

from asmrmanager.common import MUSIC_SUFFIXES
from asmrmanager.common.rj_parse import id2source_name, source_name2id
from asmrmanager.common.types import (
    LocalSourceID,
    RecoverRecord,
    RemoteSourceID,
)
from asmrmanager.config import Aria2Config
from asmrmanager.filemanager.manager import FileManager
from asmrmanager.logger import logger
from asmrmanager.spider.asmrapi import ASMRAPI

fm = FileManager.get_fm()


class DownloadError(RuntimeError):
    pass


class BackendError(DownloadError):
    pass


class FileInfo(NamedTuple):
    path: Path
    url: str
    should_download: bool
    id: int

class FileInfoWithOrder(NamedTuple):
    path: Path
    url: str
    download_order: int
    id: int


class ASMRDownloader:
    def __init__(
        self,
        api: ASMRAPI,
        json_should_download: Callable[[dict[str, Any]], bool],
        name_should_download: Callable[
            [str, Literal["directory", "file"]], int
        ],
        replace=False,
        download_method: Literal["aria2", "idm"] = "idm",
        aria2_config: Aria2Config | None = None,
        fetch_cover: bool = False,
        save_recovery: Callable[[LocalSourceID, list[RecoverRecord]], None] | None = None,
    ):
        self.api = api
        self.save_path = fm.download_path
        self.json_should_download = json_should_download
        self.save_recovery = save_recovery
        self.name_should_download = name_should_download
        self.replace = replace
        self.fetch_cover = fetch_cover
        self.download_file = (
            self.download_by_idm
            if download_method == "idm"
            else self.download_by_aria2
        )

        self.aria2_config = aria2_config
        self.download_method = download_method

        try:
            if self.download_method == "aria2":
                if self.aria2_config is None:
                    raise BackendError("aria2 configuration is required.")
                from .utils.aria2_downloader import Aria2Downloader

                self.aria2_downloader = Aria2Downloader(proxy=None)
            elif self.download_method == "idm":
                from .utils.IDMHelper import IDMHelper

                self.idm_helper_type = IDMHelper
            else:
                raise BackendError(
                    f"Unsupported download method: {self.download_method}."
                )
        except ImportError as exc:
            raise BackendError(
                f"Cannot load {self.download_method} backend; install "
                f"ASMRManager[{self.download_method}] and check its requirements."
            ) from exc

    def apply_filename_filter(
        self, file_list_with_order: list[FileInfoWithOrder]
    ) -> list[FileInfo]:
        for download_order in sorted(
            {
                i.download_order
                for i in file_list_with_order
                if i.download_order >= 1
            }
        ):
            if download_order > 1:
                logger.warning(
                    f"No audio file found to download, "
                    f"try to disable filters with order {download_order}"
                )
            if any(
                (
                        1 <= f.download_order <= download_order
                        and f.path.suffix.lower() in MUSIC_SUFFIXES
                    ) for f in file_list_with_order
            ):
                break
        else:
            raise DownloadError("No audio file found to download.")
        file_list = [
            FileInfo(
                path=f.path,
                url=f.url,
                should_download=1 <= f.download_order <= download_order,
                id=f.id,
            )
            for f in file_list_with_order
        ]
        return file_list

    async def download(
        self,
        voice_id: RemoteSourceID,
        save_path: Path | None = None,
    ) -> None:
        voice_info = await self.api.get_voice_info(voice_id)
        if voice_info is None:
            raise DownloadError(f"Failed to get info for work {voice_id}.")

        assert (
            id2source_name(source_name2id(voice_info["source_id"]))
            == voice_info["source_id"]
        )

        should_down = self.json_should_download(voice_info)
        if not should_down:
            logger.info(f"stop download {voice_id}")
            return

        tracks = await self.api.get_voice_tracks(voice_id)
        if tracks is None:
            raise DownloadError(f"Failed to get tracks for work {voice_id}.")

        if save_path is None:
            save_path = self.save_path

        voice_path = save_path / voice_info["source_id"]
        if voice_path.exists():
            logger.warning("path already exists: %s", voice_path)

        voice_path.mkdir(parents=True, exist_ok=True)

        file_list_with_order = self.get_file_list(
            tracks,
            voice_path,
        )
        logger.debug("Found %d files", len(file_list_with_order))
        file_list = self.apply_filename_filter(file_list_with_order)
        logger.debug("Prepared %d recovery records", len(file_list))

        self.save_recovery_records(file_list, voice_path)
        if self.fetch_cover and all(str(f.path.relative_to(voice_path)) != 'cover.jpg' for f in file_list):
            await self.download_cover(voice_id, voice_path)
        await self.create_dir_and_download(file_list)

    async def update(self, voice_id: RemoteSourceID) -> None:
        voice_info = await self.api.get_voice_info(voice_id, refresh=True)
        if voice_info is None:
            raise DownloadError(f"Failed to get info for work {voice_id}.")

        local_source_id = source_name2id(voice_info["source_id"])
        if local_source_id is None:
            raise DownloadError(f"Failed to convert {voice_id} to local id.")
        voice_path = fm.get_path(local_source_id, prefer="download")
        if voice_path is None:
            raise DownloadError(
                f"Failed to get the path for source id {local_source_id}."
            )
        assert voice_path.name == voice_info["source_id"]
        if not voice_path.exists():
            logger.warning("No local files for %s; updating metadata", voice_info["source_id"])

        voice_path.mkdir(parents=True, exist_ok=True)
        self.json_should_download(voice_info)

        tracks = await self.api.get_voice_tracks(voice_id)
        if tracks is None:
            raise DownloadError(f"Failed to get tracks for work {voice_id}.")

        file_list_with_order = self.get_file_list(tracks, voice_path)
        file_list = self.apply_filename_filter(file_list_with_order)
        self.save_recovery_records(file_list, voice_path)

    def save_recovery_records(
        self,
        file_list: list[FileInfo],
        voice_path: Path,
    ):
        recover = [
            {
                "path": str(file.path.relative_to(voice_path)).replace(
                    "\\", "/"
                ),
                "url": file.url,
                "should_download": file.should_download,
                "fileId": file.id,
            }
            for file in file_list
        ]
        if self.save_recovery is None:
            raise DownloadError("Recovery database storage is not configured.")
        self.save_recovery(source_name2id(voice_path.name), recover)

    async def download_by_idm(
        self, url: str, save_path: Path, file_name: str
    ) -> None:
        try:
            m = self.idm_helper_type(url, str(save_path.absolute()), file_name, 3)
        except Exception as exc:
            raise BackendError(f"Failed to initialize IDM backend: {exc}") from exc
        res = m.send_link_to_idm()
        if res != 0:
            raise RuntimeError(f"IDM submission failed with error code {res}.")

    async def download_by_aria2(
        self, url: str, save_path: Path, file_name: str
    ) -> None:
        try:
            await self.aria2_downloader.download(url, save_path, file_name)
        except Exception as exc:
            if isinstance(
                exc.__cause__ or exc, (ClientConnectionError, TimeoutError)
            ):
                raise BackendError(f"Cannot connect to aria2 RPC: {exc}") from exc
            raise

    def check_exists(self, download_file_path: Path):
        p = (
            fm.download_path
            if download_file_path.is_relative_to(fm.download_path)
            else fm.storage_path
        )
        rel_path = str(download_file_path.relative_to(p))
        return fm.check_exists(rel_path)

    async def process_download(
        self, url: str, save_path: Path, file_name: str
    ):
        # file_name = file_name.translate(
        #     str.maketrans(r'/\:*?"<>|', "_________")
        # )

        file_path = save_path / file_name
        exist_info = self.check_exists(file_path)
        if exist_info.download:
            if self.replace:
                logger.info("delete old file %s (replace mode)", file_path)
                file_path.unlink()
            else:
                logger.warning("file already exists in download, ignore it: %s", file_path)
                return
        elif exist_info.storage:
            logger.warning("file already exists in storage, ignore it: %s", file_path)
            return

        logger.info("Submitting download: %s", file_path)
        try:
            await self.download_file(url, save_path, file_name)
        except (ModuleNotFoundError, DownloadError):
            raise
        except Exception as exc:
            raise DownloadError(f"Failed to submit {file_path}: {exc}") from exc

    async def download_cover(
        self, source_id: RemoteSourceID, save_path: Path
    ) -> None:
        logger.debug("downloading cover")

        try:
            save_path.mkdir(parents=True, exist_ok=True)
            image_data = await self.api.get_cover(source_id)
            with save_path.joinpath("cover.jpg").open("wb") as f:
                f.write(image_data)
        except Exception as exc:
            logger.warning("Failed to download cover for %d: %s", source_id, exc)

    async def create_dir_and_download(self, file_list: list[FileInfo]) -> None:
        failed_files = 0
        for file_info in file_list:
            file_path = file_info.path
            if not file_info.should_download:
                logger.info("filter %s", file_path)
                continue
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                await self.process_download(
                    file_info.url, file_path.parent, file_path.name
                )
            except (ModuleNotFoundError, BackendError):
                raise
            except Exception as exc:
                failed_files += 1
                logger.error("Failed to submit %s: %s", file_path, exc)
        if failed_files:
            raise DownloadError(f"Failed to submit {failed_files} files.")

    def get_file_list(
        self,
        tracks: list[dict[str, Any]],
        voice_path: Path,
        download: int = 1,
    ) -> list[FileInfoWithOrder]:
        def filter_(name: str, type_: Literal["directory", "file"]) -> int:
            return self.name_should_download(name, type_)

        def update_download(new_download: int):
            """update download value based on global download value"""
            # assert update_download(0, 1) == 0
            # assert update_download(1, 1) == 1
            # assert update_download(2, 1) == 2
            # assert update_download(2, 3) == 2
            if download == 0 or new_download == 0:
                # both should not download
                return 0
            elif download == 1 or new_download == 1:
                # download > 1 means it is initially filtered
                # so download == 1 should be ignored
                # when there are download > 1
                return max(download, new_download)
            else:
                # for both download > 1
                # return the minimum one
                # which means a higher download priority
                return min(download, new_download)

        file_list: list[FileInfoWithOrder] = []
        folders = [track for track in tracks if track["type"] == "folder"]
        files = [track for track in tracks if track["type"] != "folder"]

        for file in files:
            file_name: str = file["title"].translate(
                str.maketrans(r'/\:*?"<>|', "_________")
            )
            file_path = voice_path / file_name

            file_hash = file["hash"].split("/")
            assert len(file_hash) == 2
            file_id = int(file_hash[1])

            file_list.append(
                FileInfoWithOrder(
                    file_path,
                    file["mediaDownloadUrl"],
                    update_download(filter_(file["title"], "file")),
                    file_id,
                )
            )

        for folder in folders:
            title: str = folder["title"].translate(
                str.maketrans(r'/\:*?"<>|', "_________")
            )
            new_path = voice_path / title
            file_list.extend(
                self.get_file_list(
                    folder["children"],
                    new_path,
                    update_download(filter_(folder["title"], "directory")),
                )
            )

        return file_list

    async def __aenter__(self) -> Self:
        if self.download_method == "aria2":
            assert self.aria2_config
            await self.aria2_downloader.create_client(
                self.aria2_config.host,
                self.aria2_config.port,
                self.aria2_config.secret,
            )
        return self

    async def __aexit__(self, *args) -> None:
        if self.download_method == "aria2":
            await self.aria2_downloader.close_client()
