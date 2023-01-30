import asyncio
import shutil
from os import makedirs, path
from typing import Any, Dict, List, Callable, Iterable, Optional
from subprocess import run, CalledProcessError

try:
    import ujson as json
except ImportError:
    import json

from aiohttp import ClientSession
from aiohttp.connector import TCPConnector

from logger import logger


# TODO 统一管理固定的参数

class ASMRSpider:
    def __init__(self, name: str, password: str, proxy: str, save_path: str,
                 download_callback: Callable[[Dict[str, Any]], Any] = None, limit: int = 3) -> None:
        self._session: Optional[ClientSession] = None  # for __aenter__
        self.name = name
        self.password = password
        self.headers = {
            "Referer": "https://www.asmr.one/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko)"
                          " Chrome/78.0.3904.108 Safari/537.36"
        }
        self.proxy = proxy
        self.limit = limit
        self.save_path = save_path
        self.download_callback = download_callback or (lambda *args, **kwargs: None)
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

    async def login(self) -> None:
        async with self._session.post(
                "https://api.asmr.one/api/auth/me",
                json={"name": self.name, "password": self.password},
                headers=self.headers,
                proxy=self.proxy,
        ) as resp:
            self.headers.update({
                "Authorization": f"Bearer {(await resp.json())['token']}",
            })

    async def get(self, route: str, **params):
        resp_json = None
        while not resp_json:
            try:
                async with self._session.get(
                        route,
                        headers=self.headers,
                        proxy=self.proxy,
                        params=params
                ) as resp:
                    resp_json = await resp.json()
                    return resp_json
            except Exception as e:
                logger.warning(f'Request {route} failed: {e}')
                await asyncio.sleep(3)

    async def download(self, voice_id: int, save_path: str = None) -> None:
        voice_info = await self.get_voice_info(voice_id)

        self.download_callback(voice_info)
        save_path = save_path or self.save_path

        voice_path = path.join(save_path, f"RJ{voice_id}")
        if path.exists(voice_path):
            logger.warning(f'path {voice_path} already exists.')

        makedirs(voice_path, exist_ok=True)
        self.create_info_file(voice_info)

        tracks = await self.get_voice_tracks(voice_id)
        if isinstance(tracks, dict) and (error_info := tracks.get('error')):
            logger.error(f'RJ{voice_id} not found, {error_info}')
            return

        self.create_dir_and_files(tracks, voice_path)

    async def get_voice_info(self, voice_id: int) -> Dict[str, Any]:
        voice_info = await self.get(f"https://api.asmr.one/api/work/{voice_id}")
        return voice_info

    async def get_voice_tracks(self, voice_id: int):
        return await self.get(f"https://api.asmr.one/api/tracks/{voice_id}")

    @staticmethod
    def download_files(url: str, save_path: str, file_name: str) -> None:
        file_name = file_name.translate(str.maketrans(r'/\:*?"<>|', "_________"))
        file_path = path.join(save_path, file_name)
        if not path.exists(file_path):
            # async with self._session.get(
            #     url, headers=self.headers, proxy=self.proxy, timeout=114514
            # ) as resp:
            #     with open(file_path, "wb") as f:
            #         f.write(await resp.read())
            try:
                logger.info(f"Downloading {file_path}")
                run(f'IDMan /d {url} /p {path.abspath(save_path)} /f "{file_name}" /a', check=True)
                # await asyncio.create_subprocess_exec(
                #     'IDMan', '/d', url,
                #     '/p', str(path.abspath(save_path)),
                #     '/f', file_name, '/a')
            except CalledProcessError as e:
                logger.error(e)
        else:
            logger.warning(f'file {file_path} already exists.')

    def create_info_file(self, voice_info: Dict[str, Any]):
        rj_id = f'RJ{str(voice_info["id"]).zfill(6)}'
        voice_path = path.join(self.save_path, rj_id)
        with open(path.join(voice_path, f"{rj_id}.json"), "w", encoding="utf-8") as f:
            json.dump(voice_info, f, ensure_ascii=False, indent=4)

    def create_dir_and_files(self, tracks: List[Dict[str, Any]], voice_path: str) -> None:
        folders = [track for track in tracks if track["type"] == "folder"]
        files = [track for track in tracks if track["type"] != "folder"]
        for file in files:
            try:
                self.download_files(
                    file["mediaDownloadUrl"], voice_path, file["title"]
                )
            except Exception as e:
                logger.error(f'Download error: {e}')
                continue
        for folder in folders:
            title = folder["title"].translate(str.maketrans(r'/\:*?"<>|', "_________"))
            new_path = path.join(voice_path, title)
            makedirs(new_path, exist_ok=True)
            self.create_dir_and_files(folder["children"], new_path)

    async def get_search_result(self, content: str, page: int, subtitle: bool):
        return await self.get(f"https://api.asmr.one/api/search/{content}", page=str(page), subtitle=str(int(subtitle)))

    async def list(self, page: int, subtitle: bool):
        return await self.get(f"https://api.asmr.one/api/works", page=str(page), subtitle=str(int(subtitle)))

    async def __aenter__(self) -> "ASMRSpider":
        self._session = ClientSession(connector=TCPConnector(limit=self.limit))
        await self.login()
        return self

    async def __aexit__(self, *args) -> None:
        await self._session.close()
