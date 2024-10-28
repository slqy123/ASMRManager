from pathlib import Path
from shutil import which
from typing import Literal
from asmrmanager.logger import logger


def convert_vtt2lrc(vtt_path: Path):
    from .vtt2lrc import vtt2lrc

    assert vtt_path.suffix == ".vtt"
    lrc_content = vtt2lrc(vtt_path)
    lrc_path = vtt_path.with_suffix(".lrc")
    if len(vtt_path.suffixes) == 2:  # formats like `audio.mp3.vtt`
        if not vtt_path.with_suffix("").exists():
            logger.warning(
                f"lyrics {vtt_path} does not have corresponding audio file"
            )
            return
        lrc_path = vtt_path.with_suffix("").with_suffix(".lrc")
    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write(lrc_content)


def convert_audio_format(
    audio_path: Path, dst: Literal["mp3", "flac", "m4a", "wav"] = "mp3"
):
    from subprocess import run

    if which("ffmpeg") is None:
        raise FileNotFoundError(
            "ffmpeg not found, please make sure you have ffmpeg installed and"
            " add it to your path"
        )

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

    run(
        [
            "ffmpeg",
            "-i",
            str(audio_path),
            "-acodec",
            *convert_args,
            str(audio_path.with_suffix(f".{dst}")),
        ],
        check=True,
    )
