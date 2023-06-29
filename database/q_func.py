from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import *

from typing import Optional


class QFunc:
    def __init__(self, ss: Session):
        self.ss = ss

    def get_info(self, rj_id: int, rand: bool):
        if rand:
            return self.ss.query(ASMR).order_by(func.random()).first()
        return self.ss.query(ASMR).get(rj_id)

    def get_tag_id(self, name: str) -> Optional[int]:
        res = self.ss.query(Tag).filter(Tag.name == name).one_or_none()
        if res:
            return res.id
        return None

    def get_tag_name(self, tid: int):
        res = self.ss.query(Tag).filter(Tag.id == tid).one_or_none()
        if res:
            return res.name
        return None

    def get_stored(self, rj_id: int):
        res = self.ss.query(ASMR).get(rj_id)
        return res.stored if res is not None else None

