from typing import List, Tuple
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Center
from textual.widgets import Button, Footer, Header, ProgressBar, Static, Label
from textual.binding import Binding
# from textual.reactive import reactive

import click
from pathlib import Path
from .player import MusicPlayer, MusicPlayerWithLyrics


class LRCPlayer(App):
    CSS_PATH = 'main.css'
    BINDINGS = [
        ('space', 'pause', ''),
        ('j', 'forward', ''),
        ('k', 'backward', ''),
        ('l', 'next_voice', ''),
        ('h', 'prev_voice', '')
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
                    self.episodes[self.voice_index][0])  # pyright: ignore
            else:
                self.players[self.voice_index] = MusicPlayerWithLyrics(
                    *self.episodes[self.voice_index])

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
            for i, l in enumerate(self.query('.lyrics')):
                assert isinstance(l, Label)
                l.update(lrc_data.lyrics[i])

        else:
            self.query_one(ProgressBar).update(progress=self.player.get_total_percent())
            for i, l in enumerate(self.query('.lyrics')):
                assert isinstance(l, Label)
                l.update(('', 'no lyrics', '')[i])

    def compose(self) -> ComposeResult:
        yield Label(self.player.title, id='title')

        for i in range(3):
            l = Label('', classes='lyrics')
            l.styles.text_opacity = str(100 - abs(1-i)*50) + '%'
            yield l

        with Center():
            yield ProgressBar(100, show_eta=False, id='pgbar')

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
        self.query_one('#title', expect_type=Label).update(self.player.title)

    def action_next_voice(self):
        if self.voice_index + 1 < len(self.episodes):
            self.switch_voice(self.voice_index + 1)

    def action_prev_voice(self):
        if self.voice_index - 1 >= 0:
            self.switch_voice(self.voice_index - 1)


@click.command()
@click.argument('path', type=click.Path(exists=True, dir_okay=True, path_type=Path))
def main(path: Path):
    import os
    # 每个元素是一个元组，包含了文件名和歌词文件名，如果没有歌词则为None
    episodes: List[Tuple[Path, Path | None]] = []
    if path.is_dir():
        for file in os.listdir(path):
            file_path = path / file
            if file_path.suffix in ('.mp3', '.wav', '.m4a', '.flac'):
                lrc_path = file_path.with_suffix('.lrc')
                if not lrc_path.exists():
                    lrc_path = None
                episodes.append((file_path, lrc_path))
    else:
        if path.suffix in ('.mp3', '.wav', '.m4a', '.flac'):
            lrc_path = path.with_suffix('.lrc')
            if not lrc_path.exists():
                lrc_path = None
            episodes.append((path, lrc_path))

    if not episodes:
        print('error input')
        return

    app = LRCPlayer(episodes)
    app.run()


if __name__ == '__main__':
    main()
