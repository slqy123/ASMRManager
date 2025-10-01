from pathlib import Path
from shutil import which
from typing import Literal, Any
import asyncio
import re

from rich.console import Console
from rich.table import Column


def convert_vtt2lrc(vtt_path: Path):
    from .vtt2lrc import vtt2lrc

    assert vtt_path.suffix == ".vtt"
    lrc_content = vtt2lrc(vtt_path)
    if len(vtt_path.suffixes) > 1 and vtt_path.suffixes[-2].lower() in (
        ".mp3",
        ".m4a",
        ".wav",
        ".flac",
    ):
        lrc_path = vtt_path.with_suffix("").with_suffix(".lrc")
    else:
        lrc_path = vtt_path.with_suffix(".lrc")

    # if len(vtt_path.suffixes) == 2:  # formats like `audio.mp3.vtt`
    # if not vtt_path.with_suffix("").exists():
    #     logger.warning(
    #         f"lyrics {vtt_path} does not have corresponding audio file"
    #     )
    #     return
    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write(lrc_content)


class AudioConverter:
    def __init__(
        self, title: str, threads: int = 6, refresh_per_second: int = 10
    ):
        from rich.progress import (
            Progress,
            SpinnerColumn,
            TextColumn,
            BarColumn,
            TaskProgressColumn,
            TimeRemainingColumn,
        )
        from rich.panel import Panel
        from rich.live import Live

        if which("ffmpeg") is None:
            raise FileNotFoundError(
                "ffmpeg not found, please make sure you have ffmpeg installed and"
                " add it to your path"
            )

        self.console = Console()
        self.progress = Progress(
            TextColumn(
                "{task.description}",
                table_column=Column(overflow="fold"),
            ),
            SpinnerColumn(),
            BarColumn(min(self.console.width // 8, 40)),
            TaskProgressColumn(),
            TimeRemainingColumn(True),
        )
        self.panel = Panel.fit(self.progress, title=title, border_style="blue")
        self.panel.subtitle = "Progress: [green]?[green]/?"
        self.semophore = asyncio.Semaphore(threads)
        self.live = Live(
            self.panel, refresh_per_second=refresh_per_second, transient=True
        )
        self.tasks_total = 0
        self.tasks_done = 0

    def update_total_progress(self):
        self.tasks_done += 1
        if self.tasks_total > 0:
            self.panel.subtitle = (
                f"Progress: [green bold]{self.tasks_done}[/green bold]"
                f"/[white]{self.tasks_total}[white]"
            )
        else:
            self.panel.subtitle = "Progress: [green bold]?[/green bold]/?"

    def __enter__(self) -> "AudioConverter":
        self.live.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.live.__exit__(exc_type, exc_val, exc_tb)

    def convert(
        self, *src: Path, dst: Literal["mp3", "flac", "m4a", "wav"] = "mp3"
    ):
        self.tasks_total = len(src)
        self.tasks_done = 0

        match dst.lower():
            case "mp3":
                convert_args = ["mp3", "-ab", "320k"]
            case "flac":
                convert_args = ["flac", "-compression_level", "5"]
            case "wav":
                convert_args = ["pcm_s16le"]
            case "m4a":
                convert_args = ["aac", "-ab", "320k"]
            case _:
                assert False

        async def _entry():
            async def thread(*args, **kwargs):
                async with self.semophore:
                    return await asyncio.to_thread(
                        self.__convert, *args, **kwargs
                    )

            await asyncio.gather(
                *map(
                    lambda x: thread(
                        x, x.with_suffix(f".{dst}"), convert_args
                    ),
                    filter(
                        lambda p: not p.is_dir()
                        and p.suffix.lower() != f".{dst}",
                        src,
                    ),
                )
            )

        asyncio.run(_entry())

    def __convert(self, src: Path, dst: Path, convert_args: list[str]):
        from subprocess import Popen, PIPE

        total_seconds = None
        task_id = None
        # prog = ffmpeg(f"output_{id_}.mp3", _iter="err")
        prog = Popen(
            [
                "ffmpeg",
                "-y",
                "-nostats",
                "-progress",
                "pipe:2",
                "-i",
                src,
                "-acodec",
                *convert_args,
                dst,
            ],
            stderr=PIPE,
            universal_newlines=True,
            bufsize=1,
            shell=False,
            errors="ignore",  # ignore broken metadata
        )
        assert prog.stderr is not None, "Process stderr is None"
        for line in prog.stderr:
            assert isinstance(line, str)
            line = line.strip()
            # Duration: 01:00:00.00
            if line.startswith("Duration: "):
                duration = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", line)
                if duration:
                    hours, minutes, seconds = map(float, duration.groups())
                    total_seconds = int(hours * 3600 + minutes * 60 + seconds)
                    task_id = self.progress.add_task(
                        str(src.name),
                        total=total_seconds,
                        start=True,
                    )
            elif line.startswith("out_time="):
                assert total_seconds is not None, "Total seconds not set"
                assert task_id is not None, "Task ID not set"
                out_time = re.search(r"out_time=(\d+):(\d+):(\d+\.\d+)", line)
                if out_time:
                    hours, minutes, seconds = map(float, out_time.groups())
                    current_seconds = int(
                        hours * 3600 + minutes * 60 + seconds
                    )
                    self.progress.update(task_id, completed=current_seconds)

        assert task_id is not None, "Task ID not set"
        self.progress.remove_task(task_id)
        self.update_total_progress()
