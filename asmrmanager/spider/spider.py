import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal

from aiohttp import ClientConnectorError, ClientSession
from aiohttp.connector import TCPConnector

from asmrmanager.common.rj_parse import RJID, id2rj
from asmrmanager.config import Aria2Config
from asmrmanager.logger import logger

try:
    IDMHELPER_EXIST = True
    from .utils.IDMHelper import IDMHelper
except (ImportError, ModuleNotFoundError):
    IDMHELPER_EXIST = False

try:
    ARIA2_EXIST = True
    from .utils.aria2_downloader import Aria2Downloader
except (ImportError, ModuleNotFoundError):
    ARIA2_EXIST = False

from typing import NamedTuple

from asmrmanager.cli.core import fm

# TODO 统一管理固定的参数

FileInfo = NamedTuple(
    "FileInfo", [("path", Path), ("url", str), ("should_download", bool)]
)


class ASMRSpider:
    # base_api_url = 'https://api.asmr.one/api/'
    base_api_url = "https://api.asmr-300.com/api/"

    def __init__(
        self,
        name: str,
        password: str,
        proxy: str,
        json_should_download: Callable[[Dict[str, Any]], bool],
        name_should_download: Callable[
            [str, Literal["directory", "file"]], bool
        ],
        replace=False,
        limit: int = 3,
        download_method: Literal["aria2", "idm"] = "idm",
        aria2_config: Aria2Config | None = None,
    ):
        # self._session: Optional[ClientSession] = None  # for __aenter__
        self._session: ClientSession
        self.name = name
        self.password = password
        self.headers = {
            "Referer": "https://www.asmr.one/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko)"
                " Chrome/78.0.3904.108 Safari/537.36"
            ),
        }
        self.proxy = proxy
        self.limit = limit
        self.save_path = fm.download_path
        # self.pop_keys = (
        #             "create_date",
        #             "userRating",
        #             "review_text",
        #             "progress",
        #             "updated_at",
        #             "user_name",
        #             "rate_count_detail",
        #             "rank"
        #     )
        self.json_should_download = json_should_download
        self.name_should_download = name_should_download
        self.replace = replace
        self.download_file = (
            self.download_by_idm
            if download_method == "idm"
            else self.download_by_aria2
        )

        self.aria2_downloader = Aria2Downloader(proxy)
        self.aria2_config = aria2_config
        self.download_method = download_method

    async def login(self) -> None:
        try:
            async with self._session.post(
                self.base_api_url + "auth/me",
                json={"name": self.name, "password": self.password},
                headers=self.headers,
                proxy=self.proxy,
            ) as resp:
                token = (await resp.json())["token"]
                self.headers.update(
                    {
                        "Authorization": f"Bearer {token}",
                    }
                )
        except ClientConnectorError as err:
            logger.error(f"Login failed, {err}")

    async def get(self, route: str, params: dict | None = None) -> Any:
        resp_json = None
        while not resp_json:
            try:
                async with self._session.get(
                    self.base_api_url + route,
                    headers=self.headers,
                    proxy=self.proxy,
                    params=params,
                ) as resp:
                    resp_json = await resp.json()
                    return resp_json
            except Exception as e:
                logger.warning(f"Request {route} failed: {e}")
                await asyncio.sleep(3)
        return resp_json

    async def post(self, route: str, data: dict | None = None) -> Any:
        resp_json = None
        while not resp_json:
            try:
                async with self._session.post(
                    self.base_api_url + route,
                    headers=self.headers,
                    proxy=self.proxy,
                    json=data,
                ) as resp:
                    resp_json = await resp.json()
                    return resp_json
            except Exception as e:
                logger.warning(f"Request {route} failed: {e}")
                await asyncio.sleep(3)
        return resp_json

    async def download(
        self,
        voice_id: int,
        save_path: Path | None = None,
    ) -> None:
        voice_info = await self.get_voice_info(voice_id)

        should_down = self.json_should_download(voice_info)
        if not should_down:
            logger.info(f"stop download {voice_id}")
            return
        if save_path is None:
            save_path = self.save_path

        voice_path = save_path / id2rj(RJID(voice_id))
        if voice_path.exists():
            logger.warning(f"path {voice_path} already exists.")

        voice_path.mkdir(parents=True, exist_ok=True)
        self.create_info_file(voice_info, voice_path=voice_path)

        tracks = await self.get_voice_tracks(voice_id)
        if isinstance(tracks, dict):
            if error_info := tracks.get("error"):
                logger.error(f"RJ{voice_id} not found, {error_info}")
                return
            else:
                logger.error("Unexpected track type: dict")
                return

        file_list = self.get_file_list(tracks, voice_path)
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
            }
            for file in file_list
        ]
        with open(voice_path / ".recover", "w", encoding="utf-8") as f:
            json.dump(recover, f, ensure_ascii=False, indent=4)

    async def get_voice_info(self, voice_id: int) -> Dict[str, Any]:
        voice_info = await self.get(f"work/{voice_id}")
        assert isinstance(voice_info, dict)
        return voice_info

    async def get_voice_tracks(self, voice_id: int):
        return await self.get(f"tracks/{voice_id}")

    @staticmethod
    async def download_by_idm(
        url: str, save_path: Path, file_name: str
    ) -> bool:
        """the save path + file should not exist,
        and the filename should be legal"""
        assert IDMHELPER_EXIST
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
        rj_name = id2rj(voice_info["id"])
        # info中有名字信息，理论上应该是一样的，但有可能为空，所以不考虑使用
        # recv_rj_name = voice_info['original_workno']
        json_path = voice_path / f"{rj_name}.json"
        if json_path.exists():
            logger.info(f"Path {json_path} already exists, update it...")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(voice_info, f, ensure_ascii=False, indent=4)

    async def create_dir_and_download(self, file_list: List[FileInfo]) -> None:
        for file_info in file_list:
            file_path = file_info.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if not file_info.should_download:
                logger.info(f"filter file {file_path}")
                # with open(
                #     file_path.with_suffix(file_path.suffix + ".info"),
                #     "w",
                #     encoding="utf-8",
                # ) as f:
                #     f.write(file["mediaDownloadUrl"])
                continue
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
        self, tracks: List[Dict[str, Any]], voice_path: Path, download=True
    ):
        file_list: List[FileInfo] = []
        folders = [track for track in tracks if track["type"] == "folder"]
        files = [track for track in tracks if track["type"] != "folder"]

        for file in files:
            file_name: str = file["title"].translate(
                str.maketrans(r'/\:*?"<>|', "_________")
            )
            file_path = voice_path / file_name

            if (not download) or (
                not self.name_should_download(file["title"], "file")
            ):
                should_download = False
            else:
                should_download = True

            file_list.append(
                FileInfo(file_path, file["mediaDownloadUrl"], should_download)
            )

        for folder in folders:
            download_ = (
                True
                if self.name_should_download(folder["title"], "directory")
                else False
            )
            title: str = folder["title"].translate(
                str.maketrans(r'/\:*?"<>|', "_________")
            )
            new_path = voice_path / title
            file_list.extend(
                self.get_file_list(
                    folder["children"], new_path, download and download_
                )
            )

        return file_list

    async def get_playlists(
        self, page, page_size: int = 12, filter_by: str = "all"
    ) -> Dict[str, Any]:
        return await self.get(
            "playlist/get-playlists",
            params={
                "page": page,
                "pageSize": page_size,
                "filterBy": filter_by,
            },
        )

    async def create_playlist(
        self, name: str, desc: str | None = None, privacy: int = 0
    ):
        # Literal['public', 'non-public', 'private']
        return await self.post(
            "playlist/create-playlist",
            data={"name": name, "desc": desc or "", "privacy": privacy},
        )

    async def add_works_to_playlist(self, rj_ids: List[RJID], pl_id: str):
        return await self.post(
            "playlist/add-works-to-playlist",
            data={"id": pl_id, "works": [id2rj(rj_id) for rj_id in rj_ids]},
        )

    async def get_search_result(
        self, content: str, params: dict
    ) -> Dict[str, Any]:
        return await self.get(f"search/{content}", params=params)

    async def list(self, params: dict) -> Dict[str, Any]:
        return await self.get("works", params=params)

    async def tag(self, tag_name: str, params: dict):
        # return await self.get(f'tags/{tag_id}/works', params=params)
        return await self.get_search_result(f"$tag:{tag_name}$", params=params)

    async def va(self, va_name: str, params: dict):
        return await self.get_search_result(f"$va:{va_name}$", params=params)

    async def __aenter__(self) -> "ASMRSpider":
        self._session = ClientSession(connector=TCPConnector(limit=self.limit))
        await self.login()
        if self.download_method == "aria2":
            assert self.aria2_config
            await self.aria2_downloader.create_client(
                self.aria2_config.host,
                self.aria2_config.port,
                self.aria2_config.secret,
            )
        return self

    async def __aexit__(self, *args) -> None:
        await self._session.close()
        await self.aria2_downloader.close_client()
