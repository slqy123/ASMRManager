from sqlalchemy.orm import Session
from .database import *

from typing import Optional

class QFunc:
    def __init__(self, ss: Session):
        self.ss = ss

    def get_info(self, rj_id: int):
        return self.ss.query(ASMR).get(rj_id)

    def get_tag_id(self, name: str) -> Optional[int]:
        res = self.ss.query(Tag).filter(Tag.name == name).one_or_none()
        if res:
            return res.id
        return None
