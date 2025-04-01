from typing import Literal

from asmrmanager.common.types import RemoteSourceID
from .asmrapi import ASMRAPI


class ASMRTagAPI(ASMRAPI):
    def __init__(
        self, name: str, password: str, proxy: str | None, limit: int
    ) -> None:
        super().__init__(name, password, proxy, limit)

    async def get_all_tags(self):
        res = await self._get_tags()
        return res

    async def attach_tags(self, tag_ids: list[int], source_id: RemoteSourceID):
        return await self._attach_tags(tag_ids, source_id)

    async def vote_tag(
        self,
        tag_id: int,
        source_id: RemoteSourceID,
        action: Literal["up", "down"],
    ):
        return await self._vote_tag(
            tag_id, source_id, True if action == "up" else False
        )
