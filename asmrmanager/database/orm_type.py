from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asmrmanager.common.rj_parse import SourceID


class ASMRInstance:
    id: "SourceID"
    remote_id: int
    title: str
    circle_name: str
    tags: list["TagInstance"]
    vas: list["VoiceActorInstance"]
    nsfw: bool
    release_date: date
    price: int
    dl_count: int
    has_subtitle: bool

    star: int
    count: int
    comment: str

    held: bool
    stored: bool


class TagInstance:
    id: int
    name: str
    jp_name: str
    cn_name: str
    en_name: str


class VoiceActorInstance:
    id: int
    name: str
