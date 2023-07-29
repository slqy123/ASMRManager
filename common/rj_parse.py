from typing import Iterable, List, NewType

RJID = NewType('RJID', int)
RJName = NewType('RJName', str)


def rj2id(rj: str) -> RJID | None:
    try:
        if rj.startswith('RJ'):
            return RJID(int(rj[2:]))
        else:
            return RJID(int(rj))
    except ValueError:
        return None


def rjs2ids(rjs: Iterable[str]) -> Iterable[RJID | None]:
    return [rj2id(rj) for rj in rjs]


def rj_name2id(rj_name: RJName) -> RJID:
    return RJID(int(rj_name[2:]))


def rj_names2ids(rjs: Iterable[RJName]) -> Iterable[RJID]:
    return [rj_name2id(rj) for rj in rjs]


def id2rj(rj_id: RJID) -> RJName:
    return RJName(f'RJ{str(rj_id).zfill(6)}')


def ids2rjs(ids: Iterable[RJID]) -> List[RJName]:
    return [id2rj(id_) for id_ in ids]


if __name__ == '__main__':
    rj = RJName('RJ123456')
    print(rj2id(rj))
