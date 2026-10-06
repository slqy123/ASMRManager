import uuid
from typing import Any, Literal, Self

from asmrmanager.common.types import (
    PRIVACY,
    PROGRESS_VALUES,
    PlayListItem,
    RemoteSourceID,
    SourceID,
)
from asmrmanager.filemanager.appdirs_ import CACHE_PATH
from asmrmanager.logger import logger
from asmrmanager.spider.auth import DEFAULT_API_URL, LoginAuth
from asmrmanager.spider.transport import APIError, HTTPTransport


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
        if isinstance(response, dict) and response.get("error"):
            raise APIError("API response reported an error.") from None
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

    async def put(
        self, route: str, data: dict | None = None, params: dict | None = None
    ) -> Any:
        response = await self.transport.request(
            "PUT", route, headers=self.auth.headers, data=data, params=params
        )
        return self._check_response(response)

    async def update_review(
        self, work_id: RemoteSourceID, changes: dict[str, Any]
    ) -> dict[str, Any]:
        if type(work_id) is not int or work_id <= 0:
            raise ValueError("Cloud work ID must be a positive integer.")
        if (
            not isinstance(changes, dict)
            or not changes
            or not set(changes) <= {"rating", "review_text", "progress"}
        ):
            raise ValueError("Review changes must contain supported fields.")
        rating = changes.get("rating")
        if rating is not None and (
            type(rating) is not int or not 0 <= rating <= 5
        ):
            raise ValueError("Rating must be null or an integer from 0 to 5.")
        if "review_text" in changes and not isinstance(
            changes["review_text"], str
        ):
            raise ValueError("Review text must be a string.")
        progress = changes.get("progress")
        if progress is not None and progress not in PROGRESS_VALUES:
            raise ValueError("Unknown listening status.")
        response = await self.put(
            "review",
            data={"work_id": work_id, **changes},
            params={"starOnly": "false"},
        )
        if not isinstance(response, dict) or not isinstance(
            response.get("message"), str
        ):
            raise APIError(
                "Invalid review update acknowledgement. The remote outcome may be unknown; check it before retrying."
            )
        return response

    async def get_current_user(self) -> dict[str, Any]:
        response = await self.get("auth/me")
        user = response.get("user") if isinstance(response, dict) else None
        if not (
            isinstance(user, dict)
            and user.get("loggedIn") is True
            and isinstance(user.get("name"), str)
            and user["name"]
            and isinstance(user.get("recommenderUuid"), str)
            and user["recommenderUuid"]
        ):
            raise APIError("Invalid authenticated user response.")
        return user

    async def get_reviews(
        self, page: int = 1, page_size: int = 20, progress: str | None = None
    ) -> dict[str, Any]:
        if any(
            type(value) is not int or value < 1 for value in (page, page_size)
        ):
            raise ValueError(
                "Review page and page size must be positive integers."
            )
        if progress is not None and progress not in PROGRESS_VALUES:
            raise ValueError("Unknown listening status.")
        params = {
            "order": "id",
            "sort": "asc",
            "page": page,
            "pageSize": page_size,
        }
        if progress is not None:
            params["filter"] = progress
        response = await self.get("review", params=params)
        if not isinstance(response, dict) or not isinstance(
            response.get("works"), list
        ):
            raise APIError("Invalid review response.")
        pagination = response.get("pagination")
        if not (
            isinstance(pagination, dict)
            and all(
                type(pagination.get(key)) is int
                for key in ("currentPage", "pageSize", "totalCount")
            )
            and pagination["currentPage"] == page
            and pagination["pageSize"] == page_size
            and pagination["totalCount"] >= 0
            and all(isinstance(work, dict) for work in response["works"])
            and len(response["works"])
            == min(
                page_size,
                max(0, pagination["totalCount"] - (page - 1) * page_size),
            )
        ):
            raise APIError("Incomplete or invalid review pagination.")
        return response

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
        works: list[str] | None = None,
    ) -> dict[str, Any]:
        response = await self.post(
            "playlist/create-playlist",
            data={
                "name": name,
                "description": desc or "",
                "privacy": privacy.value,
                "locale": "zh-CN",
                "works": works if works is not None else [],
            },
        )
        try:
            if not isinstance(response, dict) or not isinstance(
                response.get("id"), str
            ):
                raise TypeError
            uuid.UUID(response["id"])
        except (ValueError, TypeError, AttributeError):
            raise APIError(
                "Invalid playlist creation ID. Creation may have succeeded; check the cloud before retrying."
            ) from None
        return response

    async def add_works_to_playlist(
        self, source_ids: list[RemoteSourceID], pl_id: uuid.UUID
    ):
        return await self.post(
            "playlist/add-works-to-playlist",
            data={"id": str(pl_id), "works": source_ids},
        )

    async def remove_works_from_playlist(
        self, source_ids: list[RemoteSourceID], pl_id: uuid.UUID
    ):
        return await self.post(
            "playlist/remove-works-from-playlist",
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
        logger.debug("Fetching work details for source %d.", voice_id)
        try:
            voice_info = await self.get(f"work/{voice_id}")
        except APIError as exc:
            logger.error("Failed to fetch work details for source %d: %s", voice_id, exc)
            return None
        assert isinstance(voice_info, dict)
        self._voice_info_cache[voice_id] = voice_info
        return voice_info

    async def get_voice_tracks(self, voice_id: RemoteSourceID):
        try:
            tracks = await self.get(f"tracks/{voice_id}", params={"v": 2})
        except APIError as exc:
            logger.error("Failed to fetch tracks for source %d: %s", voice_id, exc)
            if str(exc).strip() == "No tracks found":
                asmr_web_url = self.base_api_url.replace(
                    "/api/", ""
                ).replace("api.", "")
                logger.error(
                    "The server may be missing files for this work.\n"
                    "Please report the issue here: "
                    f"{asmr_web_url}/work/{voice_id}"
                )
            return None
        if isinstance(tracks, dict):
            logger.error("The server returned tracks in an unexpected format (dictionary).")
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

