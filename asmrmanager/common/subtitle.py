import os
from pathlib import Path
from datetime import timedelta
from asmrmanager.logger import logger
from asmrmanager.config import config
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


def format_lrc_timestamp(seconds: float) -> str:
    total_seconds = round(seconds, 2)
    minutes = int(total_seconds // 60)
    remaining_seconds = total_seconds % 60

    secs = int(remaining_seconds)
    hundredths = int(round((remaining_seconds - secs) * 100))

    if hundredths >= 100:
        secs += 1
        hundredths -= 100

    if secs >= 60:
        minutes += 1
        secs -= 60

    return f"{minutes:02d}:{secs:02d}.{hundredths:02d}"


def format_timedelta(seconds: float) -> str:
    delta = timedelta(seconds=seconds)
    parts = []
    if delta.days > 0:
        parts.append(f"{delta.days}d")
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def generate_subtitle(
    audio_path: Path, output: Path | None, force: bool = False
):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError(
            "faster_whisper is not installed, please install asmrmanager with subtitle"
            " dependency."
        )
    subtitle_config = config.subtitle_config

    if output is None:
        output_path = audio_path.with_suffix(".lrc")
    else:
        output_path = Path(output)
        if output_path.is_dir():
            output_path = output_path / audio_path.with_suffix(".lrc").name

    if output_path.exists() and not force:
        logger.info(f"Skipping {audio_path.name}: LRC file already exists")
        return

    cpu_threads = os.cpu_count() or 4
    model = WhisperModel(
        subtitle_config.model_size,
        device=subtitle_config.device,
        cpu_threads=cpu_threads,
    )
    logger.debug(f"Using {cpu_threads} CPU threads for processing")

    segments, info = model.transcribe(
        str(audio_path),
        language=subtitle_config.language,
        vad_filter=True,
    )

    total_duration = float(info.duration) if info.duration > 0 else 1e-6

    with (
        open(output_path, "w", encoding="utf-8") as f,
        Progress(
            TextColumn("[bold blue]\\[{task.description}]"),
            BarColumn(),
            TextColumn("{task.completed:.1f}/{task.total:.1f}s"),
            TimeElapsedColumn(),
            TextColumn("<"),
            TimeRemainingColumn(),
            auto_refresh=False,
        ) as progress,
    ):
        task = progress.add_task(
            description=audio_path.name, total=total_duration, units="s"
        )

        for segment in segments:
            progress.update(
                task, advance=segment.end - progress.tasks[task].completed
            )
            progress.refresh()

            start_lrc = format_lrc_timestamp(segment.start)
            text = segment.text.strip().replace("\n", " ")
            f.write(f"[{start_lrc}] {text}\n")

        if progress.tasks[task].completed < total_duration:
            progress.update(
                task,
                advance=total_duration - progress.tasks[task].completed,
            )
