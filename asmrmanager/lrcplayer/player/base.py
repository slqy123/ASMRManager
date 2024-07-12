from dataclasses import dataclass
from pathlib import Path
from typing import List, NamedTuple

from mutagen._file import File as MutagenFile

from ..lrcparse import LRC, LyricsData

# PlayerStatus = NamedTuple(
#     "PlayerStatus",
#     [
#         ("pos", int),
#         ("index", int),
#         ("total_time", int),
#         ("playing", bool),
#         ("paused", bool),
#         ("lrc", bool),
#     ],
# )

Music = NamedTuple("Music", [("path", Path), ("lrc", Path | None)])


@dataclass
class MusicInfo:
    lrc: LRC | None = None
    total_time: int | None = None


class BasePlayer:
    STEP_TIME = 15

    def __init__(self, music_list: List[Music]) -> None:
        self.music_list = music_list
        self.music_list_len = len(music_list)
        self._index = 0
        self._music_info_list: List[MusicInfo | None] = [
            None for _ in range(self.music_list_len)
        ]

    @property
    def title(self) -> str:
        return self.current.path.stem

    def switch_music(self, index: int) -> None:
        raise NotImplementedError

    def next(self) -> None:
        if self._index + 1 < self.music_list_len:
            self._index += 1
            self.switch_music(self._index)

    def prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self.switch_music(self._index)

    @property
    def current(self):
        return self.music_list[self._index]

    @property
    def is_playing(self) -> bool:
        raise NotImplementedError

    @property
    def pos(self) -> int:
        raise NotImplementedError

    @pos.setter
    def pos(self, pos: int) -> None:
        raise NotImplementedError

    @property
    def is_paused(self) -> bool:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def unpause(self) -> None:
        raise NotImplementedError

    def play(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def forward(self) -> None:
        if self.lrc is None:
            self.pos += self.STEP_TIME * 1000
        else:
            if (index := (self.lrc.index(self.pos) + 1)) < len(self.lrc.lrc):
                self.pos = self.lrc.lrc[index][0]

    def backward(self) -> None:
        if self.lrc is None:
            self.pos -= self.STEP_TIME * 1000
        else:
            self.pos = self.lrc.lrc[self.lrc.index(self.pos) - 1][0]

    def get_lrc(self, prev: int = 1, next: int = 1) -> LyricsData:
        if self.lrc is None:
            lrcs = [""] * (prev + next + 1)
            lrcs[prev] = "No Lyrics"
            return LyricsData(int(self.percentage * 100), lrcs)
        return self.lrc.get(self.pos, prev, next)

    @property
    def info(self) -> MusicInfo:
        if (info := self._music_info_list[self._index]) is not None:
            return info
        info = self._music_info_list[self._index] = MusicInfo()
        return info

    @property
    def lrc(self) -> LRC | None:
        if (lrc_ := self.current.lrc) is None:
            return
        if self.info.lrc is None:
            self.info.lrc = LRC(lrc_, self.total_time)
        return self.info.lrc

    @property
    def total_time(self) -> int:
        if self.info.total_time is None:
            self.info.total_time = self.get_total_time()
        return self.info.total_time

    def get_total_time(self) -> int:
        return int(MutagenFile(self.current.path).info.length * 1000)  # type: ignore

    @property
    def percentage(self):
        return self.pos / self.total_time

    # def get_status(self) -> PlayerStatus:
    #     return PlayerStatus(
    #         pos=self.get_pos(),
    #         index=self.index,
    #         total_time=self.total_time,
    #         playing=self.is_playing(),
    #         paused=self.paused,
    #         lrc=self.lrc,
    #     )
