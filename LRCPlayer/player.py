import pylrc
import contextlib

with contextlib.redirect_stdout(None):
    from pygame import mixer
from pathlib import Path
from chardet import detect


def parse_lrc(lrc_str: str):
    lrc = pylrc.parse(lrc_str)
    return [(int(line.time * 1000), line.text) for line in lrc if line.text.strip()]


class MusicPlayer:
    def __init__(self, music_path: Path, lrc_path: Path | None) -> None:
        self.title = music_path.name
        if lrc_path is not None:
            content = lrc_path.read_bytes()
            encoding = detect(content)['encoding']
            self.lrc = parse_lrc(content.decode(encoding))
        else:
            self.lrc = parse_lrc('[00:00.00] no lyrics')

        self.lrc.insert(0, (-10 ** 10, ''))
        self.lrc.append((10 ** 10, ''))
        mixer.init()
        mixer.music.load(music_path)

    def get_time(self):
        return mixer.music.get_pos()

    def play(self):
        mixer.music.play()

    def pause(self):
        mixer.music.pause()

    def unpause(self):
        mixer.music.unpause()

    def get_busy(self):
        return mixer.music.get_busy()
