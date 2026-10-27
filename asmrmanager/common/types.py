import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import NewType, NotRequired, TypedDict

SourceID = NewType("SourceID", int)
SourceName = NewType("SourceName", str)
LocalSourceID = NewType("LocalSourceID", SourceID)
RemoteSourceID = NewType("RemoteSourceID", SourceID)


class PRIVACY(Enum):
    PUBLIC = 2
    NON_PUBLIC = 1
    PRIVATE = 0


@dataclass
class PlayListItem:
    id: uuid.UUID
    name: str
    privacy: PRIVACY
    desc: str
    works_count: int
    latest_work_id: SourceID | None = None

    def asdict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "privacy": self.privacy.value,
            "desc": self.desc,
            "works_count": self.works_count,
            "latest_work_id": self.latest_work_id,
        }


PROGRESS_VALUES = ("marked", "listening", "listened", "replay", "postponed")


class RecoverRecord(TypedDict):
    path: str
    url: str
    should_download: bool
    fileId: NotRequired[int | None]


def validate_recovery(records: list[RecoverRecord]) -> list[RecoverRecord]:
    if not isinstance(records, list):
        raise TypeError("Recovery records must be a list.")
    normalized = []
    paths = set()
    for record in records:
        if not isinstance(record, dict):
            raise TypeError("Recovery records must be objects.")
        path = record.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("Recovery paths must be nonempty strings.")
        relative = PurePosixPath(path.replace("\\", "/"))
        if (
            relative.is_absolute()
            or PureWindowsPath(path).drive
            or ".." in relative.parts
            or str(relative) == "."
        ):
            raise ValueError("Recovery paths must stay inside the work directory.")
        path = str(relative)
        if path in paths:
            raise ValueError("Duplicate recovery path.")
        paths.add(path)
        url = record.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("Recovery URL must be a nonempty string.")
        if type(record.get("should_download")) is not bool:
            raise ValueError("Recovery download flag must be boolean.")
        file_id = record.get("fileId")
        if file_id is not None and (type(file_id) is not int or file_id <= 0):
            raise ValueError("Recovery file ID must be a positive integer.")
        normalized.append({**record, "path": path})
    return normalized
