import typing

from sqlalchemy import func
from sqlalchemy.orm import Session

from asmrmanager.common.types import LocalSourceID
from asmrmanager.database.orm_type import ASMRInstance
from asmrmanager.logger import logger

from .database import ASMR, Tag


class QFunc:
    def __init__(self, ss: Session):
        self.ss = ss

    def get_info(
        self, local_source_id: LocalSourceID, rand: bool
    ) -> ASMRInstance | None:
        logger.debug(local_source_id)
        if rand:
            return self.ss.query(ASMR).order_by(func.random()).first()
        return self.ss.query(ASMR).get(local_source_id)

    def get_tag_id(self, name: str) -> int | None:
        res = self.ss.query(Tag).filter(Tag.name == name).one_or_none()
        if res:
            return getattr(res, "id")
        return None

    def get_tag_name(self, tid: int):
        res = self.ss.query(Tag).filter(Tag.id == tid).one_or_none()
        if res:
            return res.name
        return None

    def get_stored(self, source_id: LocalSourceID):
        res = self.ss.query(ASMR).get(source_id)
        return res.stored if res is not None else None

    def get_local_id(self, remote_id: int) -> int | None:
        res = self.ss.query(ASMR).filter_by(remote_id=remote_id).one_or_none()
        if res:
            return typing.cast(int, res.id)

    def get_remote_id(self, local_id: int) -> int | None:
        res = self.ss.query(ASMR).get(local_id)
        if res:
            return int(res.remote_id)
