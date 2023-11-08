import contextlib
from dataclasses import dataclass
from typing import List, Tuple

import pylrc

with contextlib.redirect_stdout(None):
    from pygame import mixer

from pathlib import Path

from chardet import detect
from mutagen._file import File as MutagenFile


class MusicPlayer:
    STEP_TIME = 15

    def __init__(self, music_path: Path) -> None:
        self.music_path = music_path
        self.title = music_path.name
        if mixer.get_init() is None:
            mixer.init()
        self.player = mixer.music
        self.prev_time = 0
        self.prev_pos = 0

        self.total_time = int(
            MutagenFile(music_path).info.length * 1000  # type:ignore
        )

    def is_playing(self):
        return self.player.get_busy()

    def play(self):
        self.prev_time = 0
        self.prev_pos = 0
        self.player.load(self.music_path)
        self.player.play()

    def stop(self):
        self.player.stop()

    def _get_play_time(self):
        return self.player.get_pos()

    def get_time_pass(self):
        return self._get_play_time() - self.prev_time

    def get_pos(self):
        return self.prev_pos + self.get_time_pass()

    def pause(self):
        mixer.music.pause()

    def unpause(self):
        mixer.music.unpause()

    def _set_pos(self, pos: int):
        # 对于wav类型的文件，set_pos可能会抛出错误，如果postion超出范围了的话
        try:
            self.player.set_pos(pos / 1000)
        except Exception:
            return self._set_pos(pos - 500)
        self.prev_pos = pos
        self.prev_time = self._get_play_time()

    def forward(self, t: float | None = None):
        t_ = t if t is not None else self.STEP_TIME
        dst = self.get_pos() + int(t_ * 1000)
        self._set_pos(dst)

    def backward(self, t: float | None = None):
        t_ = t if t is not None else self.STEP_TIME
        dst = self.get_pos() - int(t_ * 1000)
        self._set_pos(dst)

    def get_total_percent(self) -> int:
        return min(int(self.get_pos() / self.total_time * 100), 100)


class LyricsParser:
    @dataclass
    class LyricsData:
        progress: int
        lyrics: List[str]

    def __init__(self, lrc_path: Path, total_time: int) -> None:
        content = lrc_path.read_bytes()
        encoding = detect(content)["encoding"]
        if encoding is None:
            raise EncodingWarning("Unrecognizable encoding")
        encoding = "gbk" if encoding.upper() == "GB2312" else encoding
        self.lrc = self.parse_lrc(content.decode(encoding))

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

    def get_next_index(self, t: int):
        for i, line in enumerate(self.lrc):
            if t < line[0]:
                return i
        else:
            return -1

    def get_lrc_data_by_time(self, t: int):
        def get_by_index(idx: int):
            res = []
            for i in (idx - 2, idx - 1, idx):
                if 0 <= i < len(self.lrc):
                    res.append(self.lrc[i][1])
                else:
                    res.append("")
            return res

        idx = self.get_next_index(t)
        if idx == -1:
            t1 = t - self.lrc[-1][0]
            t2 = self.total_time - self.lrc[-1][0]

            # 对于wav文件来说，get_pos 的最大值会和 total_time 有些许出入，误差大概几百个毫秒，
            # 一般都是get_pos更大，另外total_time是准确值
            percentage = 0 if t2 == 0 else min(int(t1 / t2 * 100), 100)
            return self.LyricsData(percentage, get_by_index(len(self.lrc)))

        if idx == 0:
            return self.LyricsData(
                int(t / self.lrc[0][0] * 100) if self.lrc[0][0] != 0 else 0,
                get_by_index(idx),
            )

        if self.lrc[idx][0] - self.lrc[idx - 1][0] != 0:
            progress = int(
                (t - self.lrc[idx - 1][0])
                / (self.lrc[idx][0] - self.lrc[idx - 1][0])
                * 100
            )
        else:
            progress = 0
        return self.LyricsData(progress, get_by_index(idx))


class MusicPlayerWithLyrics(MusicPlayer, LyricsParser):
    def __init__(self, music_path: Path, lrc_path: Path) -> None:
        MusicPlayer.__init__(self, music_path)
        LyricsParser.__init__(self, lrc_path, self.total_time)

    def get_lyrics(self):
        return self.get_lrc_data_by_time(self.get_pos())

    def set_pos_by_index(self, idx: int):
        pos = self.lrc[idx][0]
        self._set_pos(pos)

    def forward_lrc(self):
        idx = self.get_next_index(self.get_pos())
        if idx == -1:
            return
        self.set_pos_by_index(idx)

    def backward_lrc(self):
        idx = self.get_next_index(self.get_pos())
        if idx in (0, 1):
            self._set_pos(0)
            return
        if idx == -1:
            self.set_pos_by_index(-2)
            return
        self.set_pos_by_index(idx - 2)


if __name__ == "__main__":
    p = MusicPlayer(
        Path(r"E:\asmr\RJ339431\1日目 はじめてのさいみん(手マン).flac")
    )
    lrc = LyricsParser(
        Path(r"E:\asmr\RJ339431\1日目 はじめてのさいみん(手マン).lrc"),
        p.total_time,
    )
    pl = MusicPlayerWithLyrics(
        Path(r"E:\asmr\RJ339431\1日目 はじめてのさいみん(手マン).flac"),
        Path(r"E:\asmr\RJ339431\1日目 はじめてのさいみん(手マン).lrc"),
    )
