import json
import time
from typing import Any, Dict, List, NamedTuple, TypeVar
from base64 import b64decode
import os

from aiohttp import ClientConnectorError, ClientSession
from aiohttp.connector import TCPConnector

from asmrmanager.common.types import RemoteSourceID
from asmrmanager.logger import logger
from asmrmanager.filemanager.appdirs_ import CACHE_PATH
from asmrmanager.spider.utils.retry import RetryError, retry

T = TypeVar("T", bound="ASMRAPI")
LoginCache = NamedTuple(
    "LoginCache",
    [
        ("token", str),
        ("recommender_uuid", str),
        ("expire_time", int),
        ("username", str),
    ],
)


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

    @property
    def login_cache(self) -> LoginCache | None:
        CACHE_PATH.mkdir(parents=True, exist_ok=True)
        login_cache_path = CACHE_PATH / "login_cache.json"
        if not login_cache_path.exists():
            return None
        try:
            with open(login_cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return LoginCache(
                    token=data["token"],
                    recommender_uuid=data["recommender_uuid"],
                    expire_time=data["expire_time"],
                    username=data.get("username", ""),
                )
        except Exception as e:
            logger.error(f"Failed to load login cache: {e}")
            return None

    @login_cache.setter
    def login_cache(self, cache: LoginCache) -> None:
        login_cache_path = CACHE_PATH / "login_cache.json"
        with open(login_cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "token": cache.token,
                    "recommender_uuid": cache.recommender_uuid,
                    "expire_time": cache.expire_time,
                    "username": cache.username,
                },
                f,
            )

    async def login(self) -> None:
        login_cache = self.login_cache
        if (
            login_cache
            and login_cache.expire_time > time.time()
            and login_cache.username == self.name
        ):
            logger.info("Using cached login token.")
            self.headers.update(
                {
                    "Authorization": f"Bearer {login_cache.token}",
                }
            )
            self.recommender_uuid = login_cache.recommender_uuid
            self.__logined = True
            return
        logger.info("Requesting new login token.")

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
                jwt_body = token.split(".")[1]
                if len(jwt_body) % 4 != 0:
                    jwt_body += "=" * (4 - len(jwt_body) % 4)
                expire_time = json.loads(b64decode(jwt_body).decode())["exp"]
                self.login_cache = LoginCache(
                    token=token,
                    recommender_uuid=self.recommender_uuid,
                    expire_time=expire_time,
                    username=self.name,
                )
        except ClientConnectorError as err:
            logger.error(f"Login failed, {err}")

    @retry()
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
                raise RetryError
        return resp_json

    @retry()
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
                raise RetryError
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


if api_channel := os.getenv("ASMR_CUSTOM_API_CHANNEL"):
    ASMRAPI.set_api_channel(api_channel)
