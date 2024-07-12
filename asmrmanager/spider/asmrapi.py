import asyncio
from typing import Any, Dict, List, TypeVar

from aiohttp import ClientConnectorError, ClientSession
from aiohttp.connector import TCPConnector

from asmrmanager.common.types import RemoteSourceID
from asmrmanager.logger import logger

T = TypeVar("T", bound="ASMRAPI")


class ASMRAPI:
    base_api_url = "https://api.asmr-200.com/api/"

    headers = {
        "Referer": "https://www.asmr.one/",
        # ---
        # 这些参数中的某一个或几个应该可以解决
        # 如RJ296187会出现的 504 Gateway Time-out 问题
        "Origin": "https://www.asmr.one",
        "Host": "api.asmr-200.com",
        "Connection": "keep-alive",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Dest": "empty",
        # ---
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/78.0.3904.108 Safari/537.36"
        ),
    }

    @classmethod
    def set_api_channel(cls, api_channel: str):
        cls.base_api_url = f"https://{api_channel}/api/"
        cls.headers["host"] = api_channel

    def __init__(
        self, name: str, password: str, proxy: str | None, limit: int
    ) -> None:
        self._session: ClientSession
        self.name = name
        self.password = password
        self.proxy = proxy
        self.limit = limit

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

    async def _get_playlists(
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

    async def _create_playlist(
        self, name: str, desc: str | None = None, privacy: int = 0
    ):
        # Literal['public', 'non-public', 'private']
        return await self.post(
            "playlist/create-playlist",
            data={
                "name": name,
                "description": desc or "",
                "privacy": privacy,
                "locale": "zh-CN",
                "works": [],
            },
        )

    async def _add_works_to_playlist(
        self, source_ids: List[RemoteSourceID], pl_id: str
    ):
        return await self.post(
            "playlist/add-works-to-playlist",
            data={"id": pl_id, "works": source_ids},
        )

    async def _delete_playlist(self, pl_id: str):
        return await self.post("playlist/delete-playlist", data={"id": pl_id})

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

    async def __aenter__(self: T) -> T:
        self._session = ClientSession(connector=TCPConnector(limit=self.limit))
        await self.login()
        return self

    async def __aexit__(self, *_) -> None:
        await self._session.close()
