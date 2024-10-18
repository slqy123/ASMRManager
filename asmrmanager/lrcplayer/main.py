import time
from pathlib import Path
from time import monotonic
from typing import List

import click
from textual.app import App, ComposeResult
from textual.containers import Center
from textual.widgets import Footer, Label, ProgressBar

from asmrmanager.common.vtt2lrc import vtt2lrc
from asmrmanager.config import config
from asmrmanager.filemanager.manager import FileManager
from asmrmanager.logger import logger

from .player.base import Music

# from textual.reactive import reactive

MUSIC_SUFFIXES = (".mp3", ".wav", ".m4a", ".flac")


class LRCPlayer(App):
    CSS_PATH = "main.css"
    BINDINGS = [
        ("space", "pause", "暂停"),
        ("j", "forward", "快进"),
        ("k", "backward", "快退"),
        ("l", "next_voice", "下一首"),
        ("h", "prev_voice", "上一首"),
    ]
    LRC_PREV = 1
    LRC_NEXT = 1
    OPERATION_FREQ = 0.05

    def __init__(self, episodes: List[Music], *args, **kwargs):
        episodes = sorted(episodes, key=lambda x: x.path)
        self.episodes = episodes
        # logger.debug(self.episodes)
        match config.player:
            case "pygame":
                from .player.pygameplayer import PyGamePlayer

                self.player = PyGamePlayer(episodes)
            case "mpd":
                from .player.mpdplayer import MPDPlayer

                self.player = MPDPlayer(episodes)
            case _:
                logger.error(f"player {config.player} not supported")
                assert False

        super().__init__(*args, **kwargs)
        self.last_operation_time = monotonic()

    def check_freq(self):
        if (
            delta := monotonic() - self.last_operation_time
        ) < self.OPERATION_FREQ:
            time.sleep(delta)

    def on_mount(self):
        self.player.play()
        self.progress_timer = self.set_interval(0.05, self.progress)

    def progress(self):
        if not self.player.is_playing:
            self.action_next_voice()
            return

        lrc_data = self.player.get_lrc(self.LRC_PREV, self.LRC_NEXT)

        self.query_one(ProgressBar).update(progress=lrc_data.progress)
        for i, lrc in enumerate(self.query(".lyrics")):
            assert isinstance(lrc, Label)
            lrc.update(lrc_data.lyrics[i])

        # 更新播放时间
        # 格式化成 x:xx / x:xx
        def format_time(seconds: int):
            return f"{seconds // 60_000}:{seconds % 60_000 // 1000:02d}"

        self.query_one("#time", expect_type=Label).update(
            f"[{format_time(self.player.pos)}"
            " / "
            f"{format_time(self.player.total_time)}]"
        )

        self.query_one("#title", expect_type=Label).update(self.player.title)

    def compose(self) -> ComposeResult:
        yield Label(self.player.title, id="title")

        for i in range(self.LRC_PREV):
            label = Label("", classes="lyrics")
            label.styles.text_opacity = (
                str(int((i + 1) / (self.LRC_PREV + 1) * 100)) + "%"
            )
            yield label
        yield Label("", classes="lyrics")

        for i in range(self.LRC_PREV):
            label = Label("", classes="lyrics")
            label.styles.text_opacity = (
                str(int((1 - (i + 1) / (self.LRC_PREV + 1)) * 100)) + "%"
            )
            yield label

        with Center():
            yield ProgressBar(100, show_eta=False, id="pgbar")
            yield Label("[0:00 / 0:00]", id="time")

        yield Footer()

    def action_pause(self):
        if not self.player.is_paused:
            self.player.pause()
            self.progress_timer.pause()
        else:
            self.player.unpause()
            self.progress_timer.resume()

    def action_forward(self):
        self.check_freq()
        self.player.forward()

    def action_backward(self):
        self.check_freq()
        self.player.backward()

    def switch_voice(self, idx: int):
        self.player.switch_music(idx)
        self.query_one("#title", expect_type=Label).update(self.player.title)

    def action_next_voice(self):
        self.player.next()
        self.query_one("#title", expect_type=Label).update(self.player.title)

    def action_prev_voice(self):
        self.player.prev()
        self.query_one("#title", expect_type=Label).update(self.player.title)


@click.command()
@click.argument(
    "path", type=click.Path(exists=True, dir_okay=True, path_type=Path)
)
def main(path: Path):
    if not (FileManager.CONFIG_PATH / "mpd.conf").exists():
        FileManager.init_mpd()

    # 每个元素是一个元组，包含了文件名和歌词文件名，如果没有歌词则为None
    episodes: List[Music] = []
    assert path.is_dir()

    for file in path.iterdir():
        if file.is_dir():
            continue

        if file.suffix not in MUSIC_SUFFIXES:
            continue

        if (lrc := file.with_suffix(".lrc")).exists():
            episodes.append(Music(file, lrc))
            continue

        if (vtt := file.with_suffix(".vtt")).exists():
            logger.info(f"convert vtt to lrc: {vtt}")
            lrc_content = vtt2lrc(vtt)
            with open(lrc, "w", encoding="utf-8") as f:
                f.write(lrc_content)
            episodes.append(Music(path, lrc))
            continue

        episodes.append(Music(file, None))

    if not episodes:
        logger.error("error input")
        return

    app = LRCPlayer(episodes)
    app.run()


if __name__ == "__main__":
    main()
