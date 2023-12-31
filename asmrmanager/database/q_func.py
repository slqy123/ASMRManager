from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from asmrmanager.database.orm_type import ASMRInstance

from .database import ASMR, Tag


class QFunc:
    def __init__(self, ss: Session):
        self.ss = ss

    def get_info(self, rj_id: int, rand: bool) -> ASMRInstance | None:
        if rand:
            return self.ss.query(ASMR).order_by(func.random()).first()
        return self.ss.query(ASMR).get(rj_id)

    def get_tag_id(self, name: str) -> Optional[int]:
        res = self.ss.query(Tag).filter(Tag.name == name).one_or_none()
        if res:
            return getattr(res, "id")
        return None

    def get_tag_name(self, tid: int):
        res = self.ss.query(Tag).filter(Tag.id == tid).one_or_none()
        if res:
            return res.name
        return None

    def get_stored(self, rj_id: int):
        res = self.ss.query(ASMR).get(rj_id)
        return res.stored if res is not None else None
