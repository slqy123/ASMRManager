import uuid
from typing import Any, Literal, Self

from asmrmanager.common.types import (
    PRIVACY,
    PlayListItem,
    RemoteSourceID,
    SourceID,
)
from asmrmanager.filemanager.appdirs_ import CACHE_PATH
from asmrmanager.logger import logger
from asmrmanager.spider.auth import DEFAULT_API_URL, LoginAuth
from asmrmanager.spider.transport import HTTPTransport


class APIError(RuntimeError):
    pass


class ASMRAPI:
    def __init__(
        self,
        name: str,
        password: str,
        proxy: str | None,
        limit: int,
        max_rps: float = 4,
        base_url: str = DEFAULT_API_URL,
    ) -> None:
        self.base_api_url = base_url
        self.auth = LoginAuth(name, password, self.base_api_url, CACHE_PATH)
        self.transport = HTTPTransport(self.base_api_url, proxy, limit, max_rps)
        self._voice_info_cache: dict[RemoteSourceID, dict[str, Any]] = {}

    async def _request_login(self, credentials: dict[str, str]) -> Any:
        return await self.transport.request(
            "POST", "auth/me", headers=self.auth.headers, data=credentials
        )

    @staticmethod
    def _check_response(response: Any) -> Any:
        if isinstance(response, dict) and (error := response.get("error")):
            raise APIError(str(error))
        return response

    async def get(self, route: str, params: dict | None = None) -> Any:
        response = await self.transport.request(
            "GET", route, headers=self.auth.headers, params=params
        )
        return self._check_response(response)

    async def post(self, route: str, data: dict | None = None) -> Any:
        response = await self.transport.request(
            "POST", route, headers=self.auth.headers, data=data
        )
        return self._check_response(response)

    async def get_playlists(
        self, page: int = 1, page_size: int = 12, filter_by: str = "all"
    ) -> tuple[list[PlayListItem], int]:
        resp = await self.get(
            "playlist/get-playlists",
            params={
                "page": page,
                "pageSize": page_size,
                "filterBy": filter_by,
            },
        )
        playlists = [
            PlayListItem(
                id=uuid.UUID(item["id"]),
                name=item["name"],
                privacy=PRIVACY(item["privacy"]),
                desc=item["description"],
                works_count=item["works_count"],
                latest_work_id=SourceID(item["latestWorkID"]),
            )
            for item in resp["playlists"]
        ]
        return playlists, resp["pagination"]["totalCount"]

    async def create_playlist(
        self,
        name: str,
        desc: str | None = None,
        privacy: PRIVACY = PRIVACY.PRIVATE,
    ):
        return await self.post(
            "playlist/create-playlist",
            data={
                "name": name,
                "description": desc or "",
                "privacy": privacy.value,
                "locale": "zh-CN",
                "works": [],
            },
        )

    async def add_works_to_playlist(
        self, source_ids: list[RemoteSourceID], pl_id: uuid.UUID
    ):
        return await self.post(
            "playlist/add-works-to-playlist",
            data={"id": str(pl_id), "works": source_ids},
        )

    async def show_works_in_playlist(
        self, pl_id: uuid.UUID, page: int = 1, page_size: int = 12
    ) -> tuple[list[Any], int]:
        resp = await self.get(
            "playlist/get-playlist-works",
            params={"id": str(pl_id), "page": page, "pageSize": page_size},
        )
        return resp["works"], resp["pagination"]["totalCount"]

    async def delete_playlist(self, pl_id: uuid.UUID):
        return await self.post(
            "playlist/delete-playlist", data={"id": str(pl_id)}
        )

    async def get_recommendations(self, page: int = 1):
        return await self.post(
            "recommender/recommend-for-user",
            data={
                "keyword": " ",
                "recommenderUuid": self.auth.recommender_uuid,
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
    ) -> dict[str, Any]:
        return await self.get(f"search/{content}", params=params)

    async def get_all_tags(self):
        return await self.get("tags/")

    async def attach_tags(self, tag_ids: list[int], source_id: RemoteSourceID):
        return await self.post(
            "vote/attach-tags-to-work",
            data={"tagIDs": tag_ids, "workID": source_id},
        )

    async def vote_tag(
        self,
        tag_id: int,
        source_id: RemoteSourceID,
        action: Literal["up", "down"],
    ):
        return await self.post(
            "vote/vote-work-tag",
            data={
                "status": 1 if action == "up" else 2,
                "tagID": tag_id,
                "workID": source_id,
            },
        )

    async def verify_hash(self, fileId: int, hash_: str):
        return await self.post(
            "media/verify-workfile-hash",
            data={
                "fileId": fileId,
                "hash": hash_.lower(),
                "UA": self.auth.headers["User-Agent"],
                "processorName": "Native",
            },
        )

    async def binary_get(
        self, route: str, params: dict | None = None
    ) -> bytes:
        return await self.transport.request(
            "GET",
            route,
            headers=self.auth.headers,
            params=params,
            binary=True,
        )

    async def get_voice_info(
        self, voice_id: RemoteSourceID, *, refresh: bool = False
    ) -> dict[str, Any] | None:
        if not refresh and voice_id in self._voice_info_cache:
            return self._voice_info_cache[voice_id]
        self._voice_info_cache.pop(voice_id, None)
        logger.debug("Get voice info: %d", voice_id)
        try:
            voice_info = await self.get(f"work/{voice_id}")
        except APIError as exc:
            logger.error("Failed to get info of %d: %s", voice_id, exc)
            return None
        assert isinstance(voice_info, dict)
        self._voice_info_cache[voice_id] = voice_info
        return voice_info

    async def get_voice_tracks(self, voice_id: RemoteSourceID):
        try:
            tracks = await self.get(f"tracks/{voice_id}", params={"v": 2})
        except APIError as exc:
            logger.error("Remote id %d error: %s", voice_id, exc)
            if str(exc).strip() == "No tracks found":
                asmr_web_url = self.base_api_url.replace(
                    "/api/", ""
                ).replace("api.", "")
                logger.error(
                    "I seems to be a problem with the server "
                    "that has missing files.\n"
                    "Try giving feedback there: "
                    f"{asmr_web_url}/work/{voice_id}"
                )
            return None
        if isinstance(tracks, dict):
            logger.error("Unexpected track type: dict")
            return None
        return tracks

    async def get_cover(self, source_id: RemoteSourceID):
        image_data = await self.binary_get(
            f"cover/{source_id}.jpg", params={"type": "main"}
        )
        return image_data

    async def list(self, params: dict) -> dict[str, Any]:
        return await self.get("works", params=params)

    async def __aenter__(self) -> Self:
        await self.transport.__aenter__()
        self._voice_info_cache.clear()
        try:
            await self.auth.login(self._request_login)
        except BaseException:
            await self.transport.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *args) -> None:
        try:
            await self.transport.__aexit__(*args)
        finally:
            self._voice_info_cache.clear()

