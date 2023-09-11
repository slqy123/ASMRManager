import asyncio
import json
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Union,
)

from aiohttp import ClientConnectorError, ClientSession
from aiohttp.connector import TCPConnector
from pathlib import Path

from logger import logger

from .utils.IDMHelper import IDMHelper
from filemanager.manager import fm
from common.rj_parse import id2rj, RJID

# TODO 统一管理固定的参数


class ASMRSpider:
    # base_api_url = 'https://api.asmr.one/api/'
    base_api_url = 'https://api.asmr-300.com/api/'

    def __init__(
        self,
        name: str,
        password: str,
        proxy: str,
        save_path: str,
        json_should_download: Callable[[Dict[str, Any]], bool],
        name_should_download: Callable[
            [str, Literal['directory', 'file']], bool
        ],
        replace=False,
        limit: int = 3,
    ):
        # self._session: Optional[ClientSession] = None  # for __aenter__
        self._session: ClientSession
        self.name = name
        self.password = password
        self.headers = {
            'Referer': 'https://www.asmr.one/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko)'
            ' Chrome/78.0.3904.108 Safari/537.36',
        }
        self.proxy = proxy
        self.limit = limit
        self.save_path = Path(save_path)
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

    async def login(self) -> None:
        try:
            async with self._session.post(
                self.base_api_url + 'auth/me',
                json={'name': self.name, 'password': self.password},
                headers=self.headers,
                proxy=self.proxy,
            ) as resp:
                token = (await resp.json())['token']
                self.headers.update(
                    {
                        'Authorization': f'Bearer {token}',
                    }
                )
        except ClientConnectorError as err:
            logger.error(f'Login failed, {err}')

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
                logger.warning(f'Request {route} failed: {e}')
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
            logger.info(f'stop download {voice_id}')
            return
        if save_path is None:
            save_path = self.save_path

        voice_path = save_path / id2rj(RJID(voice_id))
        if voice_path.exists():
            logger.warning(f'path {voice_path} already exists.')

        voice_path.mkdir(parents=True, exist_ok=True)
        self.create_info_file(voice_info)

        tracks = await self.get_voice_tracks(voice_id)
        if isinstance(tracks, dict):
            if error_info := tracks.get('error'):
                logger.error(f'RJ{voice_id} not found, {error_info}')
                return
            else:
                logger.error('Unexpected track type: dict')
                return

        self.create_dir_and_download(tracks, voice_path)

    async def get_voice_info(self, voice_id: int) -> Dict[str, Any]:
        voice_info = await self.get(f'work/{voice_id}')
        assert isinstance(voice_info, dict)
        return voice_info

    async def get_voice_tracks(self, voice_id: int):
        return await self.get(f'tracks/{voice_id}')

    @staticmethod
    def check_wav_flac_duplicate(file_path: Path) -> bool:
        """if file duplicate or already exists, return True"""
        if file_path.exists():
            logger.error(
                (
                    f'file already exists: {file_path}, please '
                    'check for the existence of the download files first'
                )
            )
            return True
        match file_path.suffix.lower():
            case '.wav':
                another_file_path = file_path.with_suffix('.flac')
                if another_file_path.exists():
                    logger.info(f'Skipping {file_path} for same flac exists')
                    return True
            case '.flac':
                another_file_path = file_path.with_suffix('.wav')
                if another_file_path.exists():
                    logger.info(f'Skipping {file_path} for same wav exists')
                    return True
            case _:
                pass

        return False

    @staticmethod
    def download_file(url: str, save_path: Path, file_name: str) -> bool:
        """the save path + file should not exist,
        and the filename should be legal"""
        m = IDMHelper(url, str(save_path.absolute()), file_name, 3)
        res = m.send_link_to_idm()
        if res != 0:
            logger.error('IDM returns an error code!')
            return False
        return True

    def process_download(self, url: str, save_path: Path, file_name: str):
        file_name = file_name.translate(
            str.maketrans(r'/\:*?"<>|', '_________')
        )
        file_path = save_path / file_name
        if not file_path.exists():
            if self.check_wav_flac_duplicate(file_path):
                return

            logger.info(f'Downloading {file_path}')
            if not self.download_file(url, save_path, file_name):
                logger.error(f'Download {file_path} failed')
                return
        else:
            logger.warning(f'file {file_path} already exists ignore this file')

    def create_info_file(self, voice_info: Dict[str, Any]):
        rj_name = id2rj(voice_info['id'])
        # info中有名字信息，理论上应该是一样的，但有可能为空，所以不考虑使用
        # recv_rj_name = voice_info['original_workno']
        json_path = self.save_path / rj_name / f'{rj_name}.json'
        if json_path.exists():
            logger.info(f'Path {json_path} already exists, update it...')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(voice_info, f, ensure_ascii=False, indent=4)

    def create_dir_and_download(
        self, tracks: List[Dict[str, Any]], voice_path: Path, download=True
    ) -> None:
        folders = [track for track in tracks if track['type'] == 'folder']
        files = [track for track in tracks if track['type'] != 'folder']
        for file in files:
            file_name: str = file['title'].translate(
                str.maketrans(r'/\:*?"<>|', '_________')
            )
            file_path = voice_path / file_name
            if (not download) or (
                not self.name_should_download(file['title'], 'file')
            ):
                logger.info(f'filter file {file_path}')
                with open(file_path.with_suffix(file_path.suffix + '.info'), 'w', encoding='utf-8') as f:
                    f.write(file['mediaDownloadUrl'])
                continue
            if file_path.exists() and self.replace:
                logger.info(f'replace mode, delete old file {file_path}')
                file_path.unlink()
            try:
                self.process_download(
                    file['mediaDownloadUrl'], voice_path, file['title']
                )
            except Exception as e:
                logger.error(f'Download error: {e}')
                continue
        for folder in folders:
            download_ = (
                True
                if self.name_should_download(folder['title'], 'directory')
                else False
            )
            title: str = folder['title'].translate(
                str.maketrans(r'/\:*?"<>|', '_________')
            )
            new_path = voice_path / title
            new_path.mkdir(parents=True, exist_ok=True)
            self.create_dir_and_download(
                folder['children'], new_path, download=download and download_
            )

    async def get_search_result(
        self, content: str, params: dict
    ) -> Dict[str, Any]:
        return await self.get(f'search/{content}', params=params)

    async def list(self, params: dict) -> Dict[str, Any]:
        return await self.get('works', params=params)

    async def tag(self, tag_name: str, params: dict):
        # return await self.get(f'tags/{tag_id}/works', params=params)
        return await self.get_search_result(f'$tag:{tag_name}$', params=params)

    async def va(self, va_name: str, params: dict):
        return await self.get_search_result(f'$va:{va_name}$', params=params)

    async def __aenter__(self) -> 'ASMRSpider':
        self._session = ClientSession(connector=TCPConnector(limit=self.limit))
        await self.login()
        return self

    async def __aexit__(self, *args) -> None:
        await self._session.close()
