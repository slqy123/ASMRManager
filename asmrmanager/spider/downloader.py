from importlib import import_module
import json
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    NamedTuple,
    TYPE_CHECKING,
    TypeVar,
)
import typing

import asyncstdlib

from asmrmanager.common.rj_parse import id2source_name, source_name2id
from asmrmanager.common.types import RemoteSourceID
from asmrmanager.config import Aria2Config
from asmrmanager.filemanager.manager import FileManager
from asmrmanager.logger import logger
from asmrmanager.spider.asmrapi import ASMRAPI

T = TypeVar("T", bound="ASMRDownloadAPI")


if TYPE_CHECKING:
    from .utils.IDMHelper import IDMHelper as _IDMHelper
    from .utils.aria2_downloader import Aria2Downloader as _Aria2Downloader

try:
    IDMHelper = typing.cast(
        "type[_IDMHelper]",
        import_module(".utils.IDMHelper", "asmrmanager.spider").IDMHelper,
    )
# except (ImportError, ModuleNotFoundError):
except Exception as _:
    # __IDMHELPER_EXIST = False
    IDMHelper = None


try:
    # __ARIA2_EXIST = True
    # from .utils.aria2_downloader import Aria2Downloader
    Aria2Downloader = typing.cast(
        "type[_Aria2Downloader]",
        import_module(
            ".utils.aria2_downloader", "asmrmanager.spider"
        ).Aria2Downloader,
    )
# except (ImportError, ModuleNotFoundError):
except Exception as _:
    # __ARIA2_EXIST = False
    Aria2Downloader = None


fm = FileManager.get_fm()

# TODO 统一管理固定的参数

FileInfo = NamedTuple(
    "FileInfo",
    [("path", Path), ("url", str), ("should_download", bool), ("id", int)],
)


class ASMRDownloadAPI(ASMRAPI):
    def __init__(
        self,
        name: str,
        password: str,
        proxy: str | None,
        json_should_download: Callable[[Dict[str, Any]], bool],
        name_should_download: Callable[
            [str, Literal["directory", "file"], bool], bool
        ],
        replace=False,
        limit: int = 3,
        download_method: Literal["aria2", "idm"] = "idm",
        aria2_config: Aria2Config | None = None,
    ):
        # self._session: Optional[ClientSession] = None  # for __aenter__
        super().__init__(name, password, proxy, limit)
        self.save_path = fm.download_path
        self.json_should_download = json_should_download
        self.name_should_download = name_should_download
        self.replace = replace
        self.download_file = (
            self.download_by_idm
            if download_method == "idm"
            else self.download_by_aria2
        )

        self.aria2_config = aria2_config
        self.download_method = download_method

        if self.download_method == "aria2":
            assert Aria2Downloader is not None, (
                "You have `download_method = aria2` configured, but failed to import corresponding class: Aria2Downloader"
            )
            # 不默认使用配置文件中的proxy，可以在aria2.conf中自行添加all-proxy配置
            self.aria2_downloader = Aria2Downloader(None)
        else:
            assert IDMHelper is not None, (
                "You have `download_method = idm` configured, but failed to import corresponding class: IDMHelper"
            )

    async def download(
        self,
        voice_id: RemoteSourceID,
        save_path: Path | None = None,
    ) -> None:
        voice_info = await self.get_voice_info(voice_id)
        assert voice_info is not None, f"Failed to download voice {voice_id}"

        should_down = self.json_should_download(voice_info)
        if not should_down:
            logger.info(f"stop download {voice_id}")
            return
        if save_path is None:
            save_path = self.save_path

        assert (
            id2source_name(source_name2id(voice_info["source_id"]))
            == voice_info["source_id"]
        )
        voice_path = save_path / voice_info["source_id"]
        if voice_path.exists():
            logger.warning(f"path {voice_path} already exists.")

        voice_path.mkdir(parents=True, exist_ok=True)
        self.create_info_file(voice_info, voice_path=voice_path)

        tracks = await self.get_voice_tracks(voice_id)
        if tracks is None:
            logger.error(
                f"Remote id {voice_id} error: failed to get tracks, skip download"
            )
            return

        file_list = self.get_file_list(
            tracks,
            voice_path,
        )
        # logger.debug(f"file_list: {
        #     list(
        #         filter(
        #             lambda f: f.should_download and f.path.suffix.lower()
        #             in (".mp3", ".wav", ".flac", ".m4a"),
        #             file_list,
        #         )
        #     )
        # }")
        if not any(
            map(
                lambda f: f.should_download
                and f.path.suffix.lower() in (".mp3", ".wav", ".flac", ".m4a"),
                file_list,
            )
        ):
            logger.warning(
                "No audio file found to download, try to disable some filters"
            )
            file_list = self.get_file_list(tracks, voice_path, disable=True)
        self.create_recover_file(file_list, voice_path)
        await self.create_dir_and_download(file_list)

    def create_recover_file(self, file_list: List[FileInfo], voice_path: Path):
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
        with open(voice_path / ".recover", "w", encoding="utf-8") as f:
            json.dump(recover, f, ensure_ascii=False, indent=4)

    @asyncstdlib.lru_cache(None)
    async def get_voice_info(
        self, voice_id: RemoteSourceID
    ) -> Dict[str, Any] | None:
        voice_info = await self.get(f"work/{voice_id}")
        assert isinstance(voice_info, dict)
        # logger.debug(f"get voice info: {voice_info}")
        if err := voice_info.get("error"):
            logger.error(f"failed to get info of {voice_id}. error: {err}")
            return None
        return voice_info

    async def get_voice_tracks(self, voice_id: RemoteSourceID):
        tracks: list[dict] | dict = await self.get(
            f"tracks/{voice_id}", params={"v": 1}
        )
        if isinstance(tracks, dict):
            if error_info := tracks.get("error"):
                logger.error(f"Remote id {voice_id} error, {error_info}")
                if error_info.strip() == "No tracks found":
                    asmr_web_url = self.base_api_url.replace(
                        "/api/", ""
                    ).replace("api.", "")
                    logger.error(
                        "I seems to be a problem with the server that has missing files.\n"
                        f"Try giving feedback there: {asmr_web_url}/work/{voice_id}"
                    )
                return None
            else:
                logger.error("Unexpected track type: dict")
                return None
        return tracks

    @staticmethod
    async def download_by_idm(
        url: str, save_path: Path, file_name: str
    ) -> bool:
        """the save path + file should not exist,
        and the filename should be legal"""
        assert IDMHelper is not None
        m = IDMHelper(url, str(save_path.absolute()), file_name, 3)
        res = m.send_link_to_idm()
        if res != 0:
            logger.error("IDM returns an error code!")
            return False
        return True

    async def download_by_aria2(
        self, url: str, save_path: Path, file_name: str
    ) -> bool:
        """the save path + file should not exist,
        and the filename should be legal"""

        await self.aria2_downloader.download(url, save_path, file_name)
        return True

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
        if exist_info.download and self.replace:
            logger.info(f"replace mode, delete old file {file_path}")
            file_path.unlink()

        if exist_info.download:
            logger.warning(
                f"file {file_path} already exists in download, ignore this"
                " file"
            )
            return

        if exist_info.storage:
            logger.warning(
                f"file {file_path} already exists in storage, ignore this file"
            )
            return

        logger.info(f"Downloading {file_path}")
        if not await self.download_file(url, save_path, file_name):
            logger.error(f"Download {file_path} failed")
            return

    def create_info_file(self, voice_info: Dict[str, Any], voice_path: Path):
        source_name = voice_info["source_id"]
        # info中有名字信息，理论上应该是一样的，但有可能为空，所以不考虑使用
        # recv_rj_name = voice_info['original_workno']
        json_path = voice_path / f"{source_name}.json"
        if json_path.exists():
            logger.info(f"Path {json_path} already exists, update it...")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(voice_info, f, ensure_ascii=False, indent=4)

    async def create_dir_and_download(self, file_list: List[FileInfo]) -> None:
        for file_info in file_list:
            file_path = file_info.path
            if not file_info.should_download:
                logger.info(f"filter file {file_path}")
                # with open(
                #     file_path.with_suffix(file_path.suffix + ".info"),
                #     "w",
                #     encoding="utf-8",
                # ) as f:
                #     f.write(file["mediaDownloadUrl"])
                continue
            file_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                await self.process_download(
                    file_info.url, file_path.parent, file_path.name
                )
            except ModuleNotFoundError as e:
                logger.critical(
                    f"Module not found: {e}, please read the install part of"
                    " the README.md to install the corresponding module"
                )
                exit(-1)
            except Exception as e:
                logger.error(f"Unknow download error: {e}")
                continue

    def get_file_list(
        self,
        tracks: List[Dict[str, Any]],
        voice_path: Path,
        disable: bool = False,  # disable some filters to get more results
        download=True,
    ):
        def filter_(name: str, type_: Literal["directory", "file"]) -> bool:
            return self.name_should_download(name, type_, disable)

        file_list: List[FileInfo] = []
        folders = [track for track in tracks if track["type"] == "folder"]
        files = [track for track in tracks if track["type"] != "folder"]

        for file in files:
            file_name: str = file["title"].translate(
                str.maketrans(r'/\:*?"<>|', "_________")
            )
            file_path = voice_path / file_name

            if (not download) or (not filter_(file["title"], "file")):
                should_download = False
            else:
                should_download = True
            file_hash = file["hash"].split("/")
            assert len(file_hash) == 2
            file_id = int(file_hash[1])

            file_list.append(
                FileInfo(
                    file_path,
                    file["mediaDownloadUrl"],
                    should_download,
                    file_id,
                )
            )

        for folder in folders:
            download_ = (
                True if filter_(folder["title"], "directory") else False
            )
            title: str = folder["title"].translate(
                str.maketrans(r'/\:*?"<>|', "_________")
            )
            new_path = voice_path / title
            file_list.extend(
                self.get_file_list(
                    folder["children"],
                    new_path,
                    disable,
                    download and download_,
                )
            )

        return file_list

    async def __aenter__(self: T) -> T:
        await super().__aenter__()

        if self.download_method == "aria2":
            assert self.aria2_config
            await self.aria2_downloader.create_client(
                self.aria2_config.host,
                self.aria2_config.port,
                self.aria2_config.secret,
            )
        return self

    async def __aexit__(self, *args) -> None:
        await super().__aexit__(*args)

        if self.download_method == "aria2":
            await self.aria2_downloader.close_client()
