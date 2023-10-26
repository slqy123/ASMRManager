from pathlib import Path
from typing import List, Tuple

import click
from textual.app import App, ComposeResult
from textual.containers import Center
from textual.widgets import Footer, Label, ProgressBar

from asmrmanager.common.vtt2lrc import vtt2lrc
from asmrmanager.logger import logger

from .player import MusicPlayer, MusicPlayerWithLyrics

# from textual.reactive import reactive


class LRCPlayer(App):
    CSS_PATH = "main.css"
    BINDINGS = [
        ("space", "pause", "暂停"),
        ("j", "forward", "快进"),
        ("k", "backward", "快退"),
        ("l", "next_voice", "下一首"),
        ("h", "prev_voice", "上一首"),
    ]

    def __init__(self, episodes: List[Tuple], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.episodes = episodes
        self.players: List[MusicPlayer | None] = [None] * len(self.episodes)
        self.voice_index = 0

    @property
    def player(self) -> MusicPlayer | MusicPlayerWithLyrics:
        if self.players[self.voice_index] is None:
            if self.episodes[self.voice_index][1] is None:
                self.players[self.voice_index] = MusicPlayer(
                    self.episodes[self.voice_index][0]
                )  # pyright: ignore
            else:
                self.players[self.voice_index] = MusicPlayerWithLyrics(
                    *self.episodes[self.voice_index]
                )

        return self.players[self.voice_index]  # pyright: ignore

    def on_mount(self):
        self.player.play()
        self.progress_timer = self.set_interval(0.05, self.progress)

    def progress(self):
        if not self.player.is_playing():
            self.action_next_voice()
            return

        if isinstance(self.player, MusicPlayerWithLyrics):
            lrc_data = self.player.get_lyrics()
            self.query_one(ProgressBar).update(progress=lrc_data.progress)
            for i, l in enumerate(self.query(".lyrics")):
                assert isinstance(l, Label)
                l.update(lrc_data.lyrics[i])

        else:
            self.query_one(ProgressBar).update(
                progress=self.player.get_total_percent()
            )
            for i, l in enumerate(self.query(".lyrics")):
                assert isinstance(l, Label)
                l.update(("", "no lyrics", "")[i])

        # 更新播放时间
        # 格式化成 x:xx / x:xx
        def format_time(seconds: int):
            return f"{seconds // 60_000}:{seconds % 60_000 // 1000:02d}"

        self.query_one("#time", expect_type=Label).update(
            f"[{format_time(self.player.get_pos())}"
            " / "
            f"{format_time(self.player.total_time)}]"
        )

    def compose(self) -> ComposeResult:
        yield Label(self.player.title, id="title")

        for i in range(3):
            label = Label("", classes="lyrics")
            label.styles.text_opacity = str(100 - abs(1 - i) * 50) + "%"
            yield label

        with Center():
            yield ProgressBar(100, show_eta=False, id="pgbar")
            yield Label("[0:00 / 0:00]", id="time")

        yield Footer()

    def action_pause(self):
        if self.player.is_playing():
            self.player.pause()
            self.progress_timer.pause()
        else:
            self.player.unpause()
            self.progress_timer.resume()

    def action_forward(self, t: float | None = None):
        if isinstance(self.player, MusicPlayerWithLyrics):
            self.player.forward_lrc()
        else:
            self.player.forward(t)

    def action_backward(self, t: float | None = None):
        if isinstance(self.player, MusicPlayerWithLyrics):
            self.player.backward_lrc()
        else:
            self.player.backward(t)

    def switch_voice(self, idx: int):
        self.voice_index = idx
        self.player.play()
        self.query_one("#title", expect_type=Label).update(self.player.title)

    def action_next_voice(self):
        if self.voice_index + 1 < len(self.episodes):
            self.switch_voice(self.voice_index + 1)

    def action_prev_voice(self):
        if self.voice_index - 1 >= 0:
            self.switch_voice(self.voice_index - 1)


@click.command()
@click.argument(
    "path", type=click.Path(exists=True, dir_okay=True, path_type=Path)
)
def main(path: Path):
    import os

    # 每个元素是一个元组，包含了文件名和歌词文件名，如果没有歌词则为None
    episodes: List[Tuple[Path, Path | None]] = []
    if path.is_dir():
        for file in os.listdir(path):
            file_path = path / file
            if file_path.suffix in (".mp3", ".wav", ".m4a", ".flac"):
                lrc_path = file_path.with_suffix(".lrc")
                if not lrc_path.exists():
                    lrc_path = None
                episodes.append((file_path, lrc_path))
    else:
        if path.suffix in (".mp3", ".wav", ".m4a", ".flac"):
            lrc_path = path.with_suffix(".lrc")
            vtt_path = path.with_suffix(path.suffix + ".vtt")
            if (not lrc_path.exists()) and (not vtt_path.exists()):
                subtitle_path = None

            match (lrc_path.exists(), vtt_path.exists()):
                case (True, True) | (True, False):
                    subtitle_path = lrc_path
                case (False, True):
                    logger.info(f"convert vtt to lrc: {vtt_path}")
                    lrc_content = vtt2lrc(vtt_path)
                    with open(lrc_path, "w", encoding="utf-8") as f:
                        f.write(lrc_content)
                    subtitle_path = lrc_path
                case _:
                    subtitle_path = None
            episodes.append((path, subtitle_path))

    if not episodes:
        print("error input")
        return

    app = LRCPlayer(episodes)
    app.run()


if __name__ == "__main__":
    main()
