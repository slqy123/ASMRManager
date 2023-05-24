from typing import List
from click.types import Tuple
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Center
from textual.widgets import Button, Footer, Header, ProgressBar, Static, Label
from textual.binding import Binding
# from textual.reactive import reactive

import click
from pathlib import Path
from .player import MusicPlayer


class LRCPlayer(App):
    CSS_PATH = 'main.css'
    BINDINGS = [
        ('space', 'pause', '')
    ]

    def __init__(self, episodes: List[Tuple] , *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.episodes = episodes
        self.players: List[MusicPlayer|None] = [None] * len(self.episodes)
        self.music_index = 0
        self.lrc_index = 1
        self.paused = False

    @property
    def player(self) -> MusicPlayer:
        if self.players[self.music_index] is None:
            self.players[self.music_index] = MusicPlayer(*self.episodes[self.music_index])  # pyright: ignore
        return self.players[self.music_index]  # pyright: ignore

    def on_mount(self):
        self.player.play()
        self.progress_timer = self.set_interval(0.05, self.progress)

    def progress(self):
        if not self.player.get_busy():
            self.music_index = (self.music_index + 1) % len(self.episodes)
            self.lrc_index = 1
            self.player.play()
            return
        t = self.player.get_time()
        t1, t2 = self.player.lrc[self.lrc_index][0], self.player.lrc[self.lrc_index + 1][0]
        if t >= t2:
            self.lrc_index += 1
            for i, l in enumerate(self.query('.lyrics')):
                assert isinstance(l, Label)
                l.update(self.player.lrc[self.lrc_index + i-1][1])
            return 

        percentage = int((t - t1) / (t2 - t1) * 100)
        self.query_one(ProgressBar).update(progress=percentage)

    def compose(self) -> ComposeResult:
        yield Label(self.player.title, id='title')

        for i in range(3):
            l = Label(self.player.lrc[i][1],classes='lyrics')
            l.styles.text_opacity = str(100 - abs(1-i)*50) + '%'
            yield l

        with Center():
            yield ProgressBar(100, show_eta=False, id='pgbar')

    def action_pause(self):
        if not self.paused:
            self.player.pause()
            self.progress_timer.pause()
        else:
            self.player.unpause()
            self.progress_timer.resume()
        self.paused = not self.paused


@click.command()
@click.argument('path', type=click.Path(exists=True, dir_okay=True, path_type=Path))
def main(path: Path):
    import os
    episodes = []
    if path.is_dir():
        for file in os.listdir(path):
            file_path = path / file
            if file_path.suffix in ('.mp3', '.wav', '.m4a'):
                lrc_path = file_path.with_suffix('.lrc') 
                if not lrc_path.exists():
                    lrc_path = None
                episodes.append((file_path, lrc_path))
    else:
        if path.suffix in ('.mp3', '.wav', '.m4a'):
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
