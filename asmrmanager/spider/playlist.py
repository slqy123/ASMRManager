import uuid
from collections.abc import Iterable
from typing import Any, List, Tuple

from asmrmanager.common.rj_parse import RJID
from asmrmanager.common.types import PRIVACY, PlayListItem

from .asmrapi import ASMRAPI


class ASMRPlayListAPI(ASMRAPI):
    def __init__(
        self, name: str, password: str, proxy: str, limit: int = 3
    ) -> None:
        super().__init__(name, password, proxy, limit)

    async def get_playlists(
        self, page: int = 1, page_size: int = 12, filter_by: str = "all"
    ) -> Tuple[List[PlayListItem], int]:
        """return a list of playlists and the total"""
        resp = await self._get_playlists(page, page_size, filter_by)
        return (
            self.process_playlists(resp["playlists"]),
            resp["pagination"]["totalCount"],
        )

    async def create_playlist(
        self,
        name: str,
        desc: str | None = None,
        privacy: PRIVACY = PRIVACY.PRIVATE,
    ):
        return await self._create_playlist(name, desc, privacy.value)

    async def add_works_to_playlist(
        self, rj_ids: Iterable[RJID], pl_id: uuid.UUID
    ):
        return await self._add_works_to_playlist(list(rj_ids), str(pl_id))

    async def delete_playlist(self, pl_id: uuid.UUID):
        return await self._delete_playlist(str(pl_id))

    def process_playlists(self, playlists: List[Any]) -> List[PlayListItem]:
        res = []
        for item in playlists:
            res.append(
                PlayListItem(
                    id=uuid.UUID(item["id"]),
                    name=item["name"],
                    privacy=PRIVACY(item["privacy"]),
                    desc=item["description"],
                    works_count=item["works_count"],
                    latest_work_id=RJID(item["latestWorkID"]),
                )
            )
        return res
