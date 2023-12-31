import bisect
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

import pylrc
from chardet import detect


@dataclass
class LyricsData:
    progress: int
    lyrics: List[str]


class LRC:
    def __init__(self, lrc_path: Path, total_time: int) -> None:
        content = lrc_path.read_bytes()
        encoding = detect(content)["encoding"]
        if encoding is None:
            raise EncodingWarning("Unrecognizable encoding")
        encoding = "gbk" if encoding.upper() == "GB2312" else encoding
        self.lrc = self.parse_lrc(content.decode(encoding))

        self.len_ = len(self.lrc)

        self.total_time = total_time

    @staticmethod
    def parse_lrc(lrc_str: str) -> List[Tuple[int, str]]:
        lrc = pylrc.parse(lrc_str)
        res = [
            (int(line.time * 1000), line.text)
            for line in lrc
            if line.text.strip()
        ]
        return sorted(res, key=lambda x: x[0])

    @lru_cache(maxsize=128)
    def index(self, t: int):
        return bisect.bisect_left(self.lrc, t, key=lambda x: x[0]) - 1

    def get_progress(self, t: int) -> int:
        index = self.index(t)
        match index + 1:
            case 0:
                return (
                    int(t / self.lrc[0][0] * 100) if self.lrc[0][0] != 0 else 0
                )
            case self.len_:
                t1 = t - self.lrc[-1][0]
                t2 = self.total_time - self.lrc[-1][0]
                return 0 if t2 <= 0 else min(int(t1 / t2 * 100), 100)
            case _:
                if self.lrc[index + 1][0] - self.lrc[index][0] > 0:
                    return int(
                        (t - self.lrc[index][0])
                        / (self.lrc[index + 1][0] - self.lrc[index][0])
                        * 100
                    )
                else:
                    return 0

    def get_lyrics(self, t: int, prev: int = 1, next: int = 1) -> List[str]:
        index = self.index(t)
        return [
            self.lrc[i][1] if i >= 0 and i < self.len_ else ""
            for i in range(index - prev, index + next + 1)
        ]

    def get(self, t: int, prev: int = 1, next: int = 1) -> LyricsData:
        return LyricsData(self.get_progress(t), self.get_lyrics(t, prev, next))
