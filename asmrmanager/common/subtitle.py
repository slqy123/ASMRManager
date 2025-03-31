import click
import os
import traceback
from tqdm import tqdm
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta
from asmrmanager.cli.core import fm, rj_argument
from asmrmanager.common.types import LocalSourceID
from asmrmanager.logger import logger
from asmrmanager.filemanager.utils import folder_chooser
from asmrmanager.config import config
from asmrmanager.lrcplayer.main import MUSIC_SUFFIXES

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

@click.command()
@rj_argument("local")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing LRC files")
@click.option("--output", "-o", type=click.Path(), help="Output file path (defaults to a .lrc file with the same name as the audio file)")
def subtitle(
    source_id: LocalSourceID,
    output: Optional[str],
    force: bool = False,
):
    """generate LRC subtitles for audio files using the Whisper model"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError(
            "faster_whisper is not installed, please install asmrmanager with subtitle"
            " dependency."
        )
    subtitle_config = config.subtitle_config

    rj_path = fm.get_path(source_id)
    if rj_path is None:
        logger.error(f"RJ id {source_id} not found!")
        return

    try:
        path = folder_chooser(
            rj_path,
            lambda _, count: bool(
                set(count.keys()).intersection(MUSIC_SUFFIXES)
            ),
        )
    except ValueError:
        logger.error(
            f"No music files{MUSIC_SUFFIXES} found, please check your local"
            " file."
        )
        exit(-1)

    assert path.is_dir()

    audio_paths: List[Path] = []
    for file in path.iterdir():
        if file.is_dir():
            continue

        if file.suffix not in MUSIC_SUFFIXES:
            continue

        audio_paths.append(file)

    if not audio_paths:
        logger.error("No audio files found in the specified directory.")
        return
    
    audio_paths.sort()

    error_count = 0
    skip_count = 0
    start_time = datetime.now()
    try:
        for audio_path in audio_paths:
            output_path = Path(output) if output else audio_path.with_suffix(".lrc")

            if output_path.exists() and not force:
                logger.info(f"Skipping {audio_path.name}: LRC file already exists")
                skip_count += 1
                continue
                
            try:
                cpu_threads = os.cpu_count() or 4
                model = WhisperModel(subtitle_config.model_size, device=subtitle_config.device, cpu_threads=cpu_threads)
                logger.debug(f"Using {cpu_threads} CPU threads for processing")
                
                segments, info = model.transcribe(
                    str(audio_path),
                    language=subtitle_config.language,
                    vad_filter=True,
                )
                
                total_duration = float(info.duration) if info.duration > 0 else 1e-6
                
                with open(output_path, "w", encoding="utf-8") as f:
                    with tqdm(
                        total=total_duration,
                        desc=f"{audio_path.name}",
                        unit="s",
                        bar_format="{l_bar}{bar}| {n:.1f}/{total:.1f}s [{elapsed}<{remaining}]"
                    ) as pbar:
                        for segment in segments:
                            pbar.update(segment.end - pbar.n)
                            
                            start_lrc = format_lrc_timestamp(segment.start)
                            text = segment.text.strip().replace('\n', ' ')
                            f.write(f"[{start_lrc}] {text}\n")
                        
                        if pbar.n < total_duration:
                            pbar.update(total_duration - pbar.n)
            except Exception as e:
                logger.error(f"Failed to process {audio_path.name}: {str(e)}\n{traceback.format_exc()}")
                error_count += 1
    except KeyboardInterrupt:
        logger.info("User interrupted, exiting...")
    finally:
        total_time = datetime.now() - start_time
        logger.info(f"Processing completed, total time: {format_timedelta(total_time.total_seconds())}")
        if skip_count > 0:
            logger.info(f"Skipped {skip_count} existing LRC files")
        if error_count > 0:
            logger.warning(f"{error_count} errors occurred")