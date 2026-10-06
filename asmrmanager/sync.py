import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from asmrmanager.common.rj_parse import id2source_name, source2id
from asmrmanager.common.types import PRIVACY, PROGRESS_VALUES, LocalSourceID
from asmrmanager.spider.asmrapi import APIError
from asmrmanager.spider.auth import AuthenticationError
from asmrmanager.spider.interface import AsyncManager


class SyncError(RuntimeError):
    pass


def local_work_id(info: dict) -> int:
    source = info.get("source_id")
    if not isinstance(source, str) or source[:2] not in ("RJ", "VJ", "BJ"):
        raise SyncError("Invalid cloud work source ID.")
    result = source2id(source)
    if result is None or not 0 < result < 5 * 10**8:
        raise SyncError("Invalid cloud work source ID.")
    if id2source_name(LocalSourceID(result))[:2] != source[:2]:
        raise SyncError("Invalid cloud work source ID.")
    if type(info.get("id")) is not int or info["id"] <= 0:
        raise SyncError("Invalid cloud work ID.")
    return result


def review_changes(work, fields) -> dict[str, Any]:
    values = {
        "star": ("rating", work.star or None),
        "comment": ("review_text", work.comment or ""),
        "progress": ("progress", work.progress),
    }
    return {values[name][0]: values[name][1] for name in fields}


def review_values(info: dict) -> dict[str, Any]:
    if not {"userRating", "review_text", "progress"} <= info.keys():
        raise SyncError("Cloud review fields are missing.")
    rating, comment, progress = (
        info[key] for key in ("userRating", "review_text", "progress")
    )
    if rating is not None and (
        type(rating) is not int or not 0 <= rating <= 5
    ):
        raise SyncError("Invalid cloud rating.")
    if comment is not None and not isinstance(comment, str):
        raise SyncError("Invalid cloud comment.")
    if progress is not None and progress not in PROGRESS_VALUES:
        raise SyncError("Unknown cloud listening status.")
    return {
        "star": rating if rating is not None else 0,
        "comment": comment if comment is not None else "",
        "progress": progress,
    }


@dataclass(frozen=True)
class PlaylistBinding:
    remote_id: uuid.UUID
    remote_service: str
    remote_user: str

    @classmethod
    def from_playlist(cls, playlist):
        return cls(
            playlist.remote_id, playlist.remote_service, playlist.remote_user
        )


@dataclass
class CloudPlaylist:
    metadata: dict
    works: dict[int, dict]


@dataclass
class Snapshot:
    reviews: dict[int, dict] = field(default_factory=dict)
    playlists: dict[uuid.UUID, CloudPlaylist] = field(default_factory=dict)
    works: dict[int, dict] = field(default_factory=dict)


class CloudSync(AsyncManager):
    def __init__(self, api):
        super().__init__(api)
        url = urlsplit(api.base_api_url)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path.rstrip("/") != "/api"
        ):
            raise SyncError("Invalid synchronization service address.")
        self.service = api.base_api_url.rstrip("/")
        self.user = None

    async def __aenter__(self):
        self.user = None
        return await super().__aenter__()

    def run(self, *tasks):
        try:
            return super().run(*tasks)
        except SyncError:
            raise
        except (
            APIError,
            AuthenticationError,
            ValueError,
            TypeError,
            KeyError,
            AssertionError,
            OSError,
        ):
            raise SyncError(
                "Cloud synchronization failed. The remote state may have changed; check it before retrying. No automatic write retry was made."
            ) from None

    async def identify(self):
        if self.user is None:
            user = await self.api.get_current_user()
            if user["name"] != self.api.auth.name:
                raise SyncError(
                    "Authenticated account does not match the configured account; no cloud update was sent."
                )
            self.user = user["name"]
        return self.user

    async def work(self, local_id, remote_id):
        if type(remote_id) is not int or remote_id <= 0:
            raise SyncError(
                "Cloud work mapping is missing; refresh the work metadata before syncing."
            )
        info = await self.api.get(f"work/{remote_id}")
        if (
            not isinstance(info, dict)
            or local_work_id(info) != local_id
            or info["id"] != remote_id
        ):
            raise SyncError(
                "Cloud work mapping does not match the local work; no cloud update was sent."
            )
        return info

    async def push_review(self, local_id, remote_id, changes):
        await self.identify()
        await self.work(local_id, remote_id)
        return await self.api.update_review(remote_id, changes)

    async def pages(self, route, key, page_key="page", params=None):
        async def fetch(page):
            if route == "review":
                return await self.api.get_reviews(page=page, page_size=20)
            return await self.api.get(
                route, params={**(params or {}), "page": page, "pageSize": 20}
            )

        results = []
        seen = set()
        total = None
        first_ids = None
        page = 1
        while True:
            response = await fetch(page)
            if not isinstance(response, dict) or not isinstance(
                response.get(key), list
            ):
                raise SyncError("Invalid cloud page.")
            pagination = response.get("pagination")
            if not isinstance(pagination, dict) or any(
                type(pagination.get(name)) is not int
                for name in (page_key, "pageSize", "totalCount")
            ):
                raise SyncError("Missing cloud pagination.")
            count = pagination["totalCount"]
            if (
                pagination[page_key] != page
                or pagination["pageSize"] != 20
                or count < 0
                or (total is not None and total != count)
            ):
                raise SyncError(
                    "Cloud pagination changed; nothing was applied."
                )
            total = count
            items = response[key]
            if len(items) != min(20, max(0, total - (page - 1) * 20)):
                raise SyncError("Incomplete cloud page; nothing was applied.")
            ids = []
            for item in items:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("id"), (int, str))
                    or isinstance(item["id"], bool)
                ):
                    raise SyncError("Invalid cloud item ID.")
                if item["id"] in seen:
                    raise SyncError(
                        "Duplicate cloud item; nothing was applied."
                    )
                seen.add(item["id"])
                ids.append(item["id"])
            if first_ids is None:
                first_ids = ids
            results.extend(items)
            if len(results) == total:
                break
            page += 1
        check = await fetch(1)
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("pagination"), dict)
            or check["pagination"]
            != {page_key: 1, "pageSize": 20, "totalCount": total}
            or not isinstance(check.get(key), list)
            or any(not isinstance(item, dict) for item in check[key])
            or [item.get("id") for item in check[key]] != first_ids
        ):
            raise SyncError(
                "Cloud data changed during collection; nothing was applied."
            )
        return results

    def binding(self, playlist):
        if playlist.remote_id is None:
            raise SyncError(
                "Playlist is not linked; use asmr pl publish or asmr pl link first."
            )
        if (
            playlist.remote_service != self.service
            or playlist.remote_user != self.user
        ):
            raise SyncError(
                "Playlist belongs to a different service or account; no cloud update was sent."
            )

    async def metadata(self, remote_id):
        await self.identify()
        data = await self.api.get(
            "playlist/get-playlist-metadata", params={"id": str(remote_id)}
        )
        self.validate_metadata(data)
        if uuid.UUID(data["id"]) != remote_id:
            raise SyncError("Cloud playlist ID mismatch.")
        return data

    def validate_metadata(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise SyncError("Invalid cloud playlist metadata.")
        try:
            uuid.UUID(data["id"])
        except ValueError:
            raise SyncError("Invalid cloud playlist ID.") from None
        if data.get("user_name") != self.user:
            raise SyncError(
                "Cloud playlist is not owned by the authenticated account."
            )
        if (
            not isinstance(data.get("name"), str)
            or not data["name"].strip()
            or not isinstance(data.get("description"), str)
            or type(data.get("privacy")) is not int
            or data["privacy"] not in (0, 1, 2)
            or type(data.get("works_count")) is not int
            or data["works_count"] < 0
        ):
            raise SyncError("Invalid cloud playlist metadata fields.")

    async def members(self, remote_id):
        rows = await self.pages(
            "playlist/get-playlist-works",
            "works",
            params={"id": str(remote_id)},
        )
        result = {}
        for row in rows:
            local_id = local_work_id(row)
            if local_id in result:
                raise SyncError("Duplicate cloud work mapping.")
            result[local_id] = row
        return result

    async def owned(self):
        await self.identify()
        rows = await self.pages(
            "playlist/get-playlists", "playlists", params={"filterBy": "owned"}
        )
        result = {}
        for row in rows:
            self.validate_metadata(row)
            remote_id = uuid.UUID(row["id"])
            if remote_id in result:
                raise SyncError("Duplicate cloud playlist ID.")
            result[remote_id] = row
        return result

    async def publish(self, name, description, privacy, works):
        await self.identify()
        sources = []
        for local_id, remote_id in works:
            sources.append((await self.work(local_id, remote_id))["source_id"])
        created = await self.api.create_playlist(
            name, description, PRIVACY(privacy), works=sources
        )
        remote_id = uuid.UUID(created["id"])
        try:
            self.validate_metadata(created)
        except SyncError:
            raise SyncError(
                f"Cloud creation returned unexpected metadata; inspect possible cloud ID {remote_id} before retrying."
            ) from None
        return created

    async def verify_publication(self, remote_id, local_ids):
        await self.metadata(remote_id)
        members = await self.members(remote_id)
        if set(members) != set(local_ids):
            raise SyncError(
                f"Cloud playlist {remote_id} was created, but members are incomplete or different. Use sync pull or link to recover; do not create it again."
            )

    async def link(self, remote_id):
        owned = await self.owned()
        if remote_id not in owned:
            raise SyncError(
                "Cloud playlist is not in the authenticated account's owned lists."
            )
        return await self.metadata(remote_id)

    async def add(self, playlist, works):
        await self.identify()
        self.binding(playlist)
        await self.metadata(playlist.remote_id)
        ids = []
        for local_id, remote_id in works:
            await self.work(local_id, remote_id)
            ids.append(remote_id)
        response = await self.api.add_works_to_playlist(
            list(dict.fromkeys(ids)), playlist.remote_id
        )
        self.member_ack(response, playlist.remote_id)
        members = await self.members(playlist.remote_id)
        if not {local_id for local_id, _ in works} <= members.keys():
            raise SyncError(
                "Cloud membership update is incomplete; local members were kept. Use sync pull to inspect it."
            )

    @staticmethod
    def member_ack(response, remote_id):
        if (
            not isinstance(response, dict)
            or response.get("id") != str(remote_id)
            or type(response.get("rowCount")) is not int
            or response["rowCount"] < 0
        ):
            raise SyncError(
                "Cloud member acknowledgement is invalid; inspect the cloud before retrying."
            )

    async def remove(self, playlists):
        await self.identify()
        for playlist in playlists:
            self.binding(playlist)
            await self.metadata(playlist.remote_id)
        for playlist in playlists:
            response = await self.api.delete_playlist(playlist.remote_id)
            if not isinstance(response, dict) or response.get("id") != str(
                playlist.remote_id
            ):
                raise SyncError(
                    "Cloud deletion acknowledgement is invalid. Some cloud lists may have been deleted; local lists were kept. Use sync pull."
                )

    async def snapshot(self, review_enabled, playlist_enabled, existing_ids):
        await self.identify()
        snapshot = Snapshot()
        if review_enabled:
            rows = await self.pages("review", "works", "currentPage")
            for row in rows:
                if row.get("user_name") != self.user:
                    raise SyncError(
                        "Cloud review owner mismatch; nothing was applied."
                    )
                local_id = local_work_id(row)
                review_values(row)
                if local_id in snapshot.reviews:
                    raise SyncError("Duplicate cloud review mapping.")
                snapshot.reviews[local_id] = row
                snapshot.works[local_id] = row
        if playlist_enabled:
            owned = await self.owned()
            for remote_id in owned:
                metadata = await self.metadata(remote_id)
                members = await self.members(remote_id)
                final_metadata = await self.metadata(remote_id)
                if final_metadata != metadata or metadata[
                    "works_count"
                ] != len(members):
                    raise SyncError(
                        "Cloud playlist changed during collection; nothing was applied."
                    )
                snapshot.playlists[remote_id] = CloudPlaylist(
                    metadata, members
                )
                for local_id, info in members.items():
                    if (
                        local_id in snapshot.works
                        and snapshot.works[local_id]["id"] != info["id"]
                    ):
                        raise SyncError(
                            "Conflicting cloud work mappings; nothing was applied."
                        )
                snapshot.works.update(members)
            if await self.owned() != owned:
                raise SyncError(
                    "Cloud playlist collection changed; nothing was applied."
                )
        for local_id, info in list(snapshot.works.items()):
            if local_id not in existing_ids:
                snapshot.works[local_id] = await self.work(
                    local_id, info["id"]
                )
        return snapshot
