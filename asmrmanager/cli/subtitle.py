from pathlib import Path
from typing import Optional, List
import traceback
from datetime import datetime, timedelta
from faster_whisper import WhisperModel
from tqdm import tqdm
import click
from asmrmanager.cli.core import fm, rj_argument
from asmrmanager.common.types import LocalSourceID
from asmrmanager.logger import logger
import os

def get_audio_files(rj_path: Path) -> List[Path]:
    return [
        f
        for f in rj_path.rglob("*.*")
        if f.suffix.lower() in [".mp3", ".wav", ".flac", ".m4a"]
    ]

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
@click.argument("audio_file", type=click.Path(exists=True), required=False)
@rj_argument("local")
@click.option("--model-size", "-m", default="base", help="Size of the Whisper model (e.g., tiny, base, small, medium, large)")
@click.option("--output", "-o", type=click.Path(), help="Output file path (defaults to a .lrc file with the same name as the audio file)")
@click.option("--language", "-l", default="ja", help="Language to be recognized (e.g., ja, en, zh)")
@click.option("--device", "-d", default="auto", help="Computing device (e.g., cpu, cuda, auto)")
@click.option("--single", "-s", is_flag=True, help="Process only the first file (valid when no specific audio file is provided)")
def subtitle(
    audio_file: Optional[str],
    source_id: LocalSourceID,
    model_size: str,
    output: Optional[str],
    language: Optional[str],
    device: str,
    single: bool,
):
    """generate LRC subtitles for audio files using the Whisper model"""
    if audio_file:
        audio_files = [Path(audio_file)]
    else:
        rj_path = fm.get_path(source_id)
        if not rj_path:
            logger.error(f"RJ{source_id} not found")
            return
        audio_files = get_audio_files(rj_path)
        audio_files.sort()
        if single:
            audio_files = audio_files[:1]

    error_count = 0
    start_time = datetime.now()
    try:
        for audio_path in audio_files:
            output_path = Path(output) if output else audio_path.with_suffix(".lrc")
            try:
                cpu_threads = os.cpu_count() or 4
                model = WhisperModel(model_size, device=device, cpu_threads=cpu_threads)
                logger.debug(f"Using {cpu_threads} CPU threads for processing")
                
                segments, info = model.transcribe(
                    str(audio_path),
                    language=language,
                    vad_filter=True,
                )
                
                total_duration = float(info.duration) if info.duration > 0 else 1e-6
                
                with open(output_path, "w", encoding="utf-8") as f:
                    with tqdm(
                        total=total_duration,
                        desc=f"{audio_path.name}",
                        unit="s",
                        bar_format="{l_bar}{bar}| {n:.1f}/{total:.1f}s [{elapsed}<{remaining}, ETA: {eta}]"
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
        if error_count > 0:
            logger.warning(f"{error_count} errors occurred")