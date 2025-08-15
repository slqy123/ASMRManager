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
        "User-Agent": "ASMRManager (https://github.com/slqy123/ASMRManager)",
    }

    @classmethod
    def set_api_channel(cls, api_channel: str):
        cls.base_api_url = f"https://{api_channel}/api/"
        # cls.headers["Host"] = api_channel

    def __init__(
        self, name: str, password: str, proxy: str | None, limit: int
    ) -> None:
        self._session: ClientSession
        self.name = name
        self.password = password
        self.proxy = proxy
        self.limit = limit
        self.recommender_uuid: str = ""
        self.__logined = False

    async def login(self) -> None:
        try:
            async with self._session.post(
                self.base_api_url + "auth/me",
                json={"name": self.name, "password": self.password},
                headers=self.headers,
                proxy=self.proxy,
            ) as resp:
                resp_json = await resp.json()
                token = resp_json["token"]
                self.headers.update(
                    {
                        "Authorization": f"Bearer {token}",
                    }
                )
                self.recommender_uuid = resp_json["user"]["recommenderUuid"]
                self.__logined = True
        except ClientConnectorError as err:
            logger.error(f"Login failed, {err}")

    async def get(
        self, route: str, params: dict | None = None, max_retry: int = 5
    ) -> Any:
        retry = 0
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
                if retry >= max_retry:
                    logger.error(f"Max retries reached for {route}.")
                    exit(-1)
                retry += 1
                await asyncio.sleep(3)
        return resp_json

    async def post(
        self, route: str, data: dict | None = None, max_retry: int = 5
    ) -> Any:
        retry = 0
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
                if retry >= max_retry:
                    logger.error(f"Max retries reached for {route}.")
                    exit(-1)
                retry += 1
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

    async def _show_works_in_playlist(
        self, pl_id: str, page: int = 1, page_size: int = 12
    ):
        return await self.get(
            "playlist/get-playlist-works",
            params={"id": pl_id, "page": page, "pageSize": page_size},
        )

    async def _delete_playlist(self, pl_id: str):
        return await self.post("playlist/delete-playlist", data={"id": pl_id})

    async def get_recommendations(self, page: int = 1):
        return await self.post(
            "recommender/recommend-for-user",
            data={
                "keyword": " ",
                "recommenderUuid": self.recommender_uuid,
                "page": page,
                "subtitle": 0,
                "localSubtitledWorks": [],
                "withPlaylistStatus": [],
            },
        )

    async def get_popular(self, page: int = 1):
        return await self.post(
            "recommender/popular",
            data={
                "keyword": " ",
                "page": page,
                "subtitle": 0,
                "localSubtitledWorks": [],
                "withPlaylistStatus": [],
            },
        )

    async def get_search_result(
        self, content: str, params: dict
    ) -> Dict[str, Any]:
        return await self.get(f"search/{content}", params=params)

    async def _get_tags(self):
        return await self.get("tags/")

    async def _attach_tags(self, tag_ids: list[int], work_id: int):
        return await self.post(
            "vote/attach-tags-to-work",
            data={"tagIDs": tag_ids, "workID": work_id},
        )

    async def _vote_tag(self, tag_id: int, work_id: int, up: bool):
        return await self.post(
            "vote/vote-work-tag",
            data={
                "status": 1 if up else 2,
                "tagID": tag_id,
                "workID": work_id,
            },
        )

    async def verify_hash(self, fileId: int, hash_: str):
        return await self.post(
            "media/verify-workfile-hash",
            data={
                "fileId": fileId,
                "hash": hash_.lower(),
                "UA": self.headers["User-Agent"],
                "processorName": "Native",
            },
        )

    async def list(self, params: dict) -> Dict[str, Any]:
        return await self.get("works", params=params)

    async def tag(self, tag_name: str, params: dict):
        # return await self.get(f'tags/{tag_id}/works', params=params)
        return await self.get_search_result(f"$tag:{tag_name}$", params=params)

    async def va(self, va_name: str, params: dict):
        return await self.get_search_result(f"$va:{va_name}$", params=params)

    async def __aenter__(self: T) -> T:
        self._session = ClientSession(connector=TCPConnector(limit=self.limit))
        if not self.__logined:
            await self.login()
        return self

    async def __aexit__(self, *_) -> None:
        await self._session.close()
