import uuid
from typing import Any, Literal, Self

import asyncstdlib

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

    async def _request_login(self, credentials: dict[str, str]) -> Any:
        return await self.transport.request(
            "POST", "auth/me", headers=self.auth.headers, data=credentials
        )

    async def get(self, route: str, params: dict | None = None) -> Any:
        return await self.transport.request(
            "GET", route, headers=self.auth.headers, params=params
        )

    async def post(self, route: str, data: dict | None = None) -> Any:
        return await self.transport.request(
            "POST", route, headers=self.auth.headers, data=data
        )

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

    @asyncstdlib.lru_cache(None)
    async def get_voice_info(
        self, voice_id: RemoteSourceID
    ) -> dict[str, Any] | None:
        logger.debug("Get voice info: %d", voice_id)
        voice_info = await self.get(f"work/{voice_id}")
        assert isinstance(voice_info, dict)
        if err := voice_info.get("error"):
            logger.error(f"failed to get info of {voice_id}. error: {err}")
            return None
        return voice_info

    async def get_voice_tracks(self, voice_id: RemoteSourceID):
        tracks: list[dict] | dict = await self.get(
            f"tracks/{voice_id}", params={"v": 2}
        )
        if isinstance(tracks, dict):
            if error_info := tracks.get("error"):
                logger.error(f"Remote id {voice_id} error, {error_info}")
                if error_info.strip() == "No tracks found":
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
            else:
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

    async def tag(self, tag_name: str, params: dict):
        # return await self.get(f'tags/{tag_id}/works', params=params)
        return await self.get_search_result(f"$tag:{tag_name}$", params=params)

    async def va(self, va_name: str, params: dict):
        return await self.get_search_result(f"$va:{va_name}$", params=params)

    async def __aenter__(self) -> Self:
        await self.transport.__aenter__()
        try:
            await self.auth.login(self._request_login)
        except BaseException:
            await self.transport.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *args) -> None:
        await self.transport.__aexit__(*args)

