from typing import Iterable, List

from .types import LocalSourceID, RemoteSourceID, SourceID, SourceName


def source2id(source: str) -> SourceID | None:
    try:
        match source[:2]:
            case "RJ":
                return SourceID(int(source[2:]))
            case "VJ":
                return SourceID(int(source[2:]) + 3 * 10**8)
            case "BJ":
                return SourceID(int(source[2:]) + 4 * 10**8)
            case _:
                return SourceID(int(source))
    except ValueError:
        return None


def is_local_source_id(source_id: SourceID) -> bool:
    return source_id < 10**8 or source_id >= 3 * 10**8


def is_remote_source_id(source_id: SourceID) -> bool:
    return source_id < 3 * 10**8


def sources2ids(sources: Iterable[str]) -> Iterable[SourceID | None]:
    return [source2id(source) for source in sources]


def source_name2id(source_name: SourceName) -> LocalSourceID:
    source_id = source2id(source_name)
    assert source_id is not None
    return LocalSourceID(source_id)


def source_names2ids(
    source_ids: Iterable[SourceName],
) -> Iterable[LocalSourceID]:
    return [source_name2id(source_id) for source_id in source_ids]


def id2source_name(source_id: LocalSourceID) -> SourceName:
    prefix = ("RJ", None, None, "VJ", "BJ")[source_id // 10**8]
    assert prefix is not None
    suffix_id = source_id % (10**8)
    source = str(suffix_id).zfill(6)
    if len(source) == 7:
        source = source.zfill(8)

    return SourceName(f"{prefix}{source}")


def ids2source_names(source_ids: Iterable[LocalSourceID]) -> List[SourceName]:
    return [id2source_name(id_) for id_ in source_ids]


if __name__ == "__main__":
    rj = SourceName("RJ123456")
    print(source2id(rj))
