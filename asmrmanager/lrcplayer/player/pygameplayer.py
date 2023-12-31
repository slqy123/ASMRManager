import contextlib
from typing import List

from .base import BasePlayer, Music

try:
    with contextlib.redirect_stdout(None):
        from pygame import mixer
except ImportError:
    raise ImportError(
        "pygame is not installed, please install asmrmanager with pygame"
        " dpendency."
    )


class PyGamePlayer(BasePlayer):
    def __init__(self, music_list: List[Music]) -> None:
        super().__init__(music_list)
        if mixer.get_init() is None:
            mixer.init()
        self.player = mixer.music
        self.prev_time = 0
        self.prev_pos = 0

    @property
    def is_playing(self) -> bool:
        return self.player.get_busy()

    def play(self):
        self.prev_time = 0
        self.prev_pos = 0
        self.player.load(self.current.path)
        self.player.play()

    def stop(self):
        self.player.stop()

    def _get_play_time(self):
        return self.player.get_pos()

    def get_time_pass(self):
        return self._get_play_time() - self.prev_time

    @property
    def pos(self):
        return self.prev_pos + self.get_time_pass()

    @pos.setter
    def pos(self, pos: int):
        # 对于wav类型的文件，set_pos可能会抛出错误，如果postion超出范围了的话
        pos = max(pos, 0)
        try:
            self.player.set_pos(pos / 1000)
        except Exception:
            self.pos = pos - 500
            return
        self.prev_pos = pos
        self.prev_time = self._get_play_time()

    def pause(self):
        mixer.music.pause()

    def unpause(self):
        mixer.music.unpause()

    @property
    def is_paused(self) -> bool:
        return not self.player.get_busy()

    def switch_music(self, index: int) -> None:
        self._index = index
        self.play()
