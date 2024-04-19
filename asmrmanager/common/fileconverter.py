from pathlib import Path
from shutil import which
from typing import Literal


def convert_vtt2lrc(vtt_path: Path):
    from .vtt2lrc import vtt2lrc

    assert vtt_path.suffix == ".vtt"
    lrc_content = vtt2lrc(vtt_path)
    with open(vtt_path.with_suffix(".lrc"), "w", encoding="utf-8") as f:
        f.write(lrc_content)


def convert_audio_format(
    audio_path: Path, dst: Literal["mp3", "flac", "wav"] = "mp3"
):
    from subprocess import run

    if which("ffmpeg") is None:
        raise FileNotFoundError(
            "ffmpeg not found, please make sure you have ffmpeg installed and"
            " add it to your path"
        )

    match dst:
        case "mp3":
            convert_args = ["mp3", "-ab", "256k"]
        case "flac":
            convert_args = ["flac"]
        case "wav":
            convert_args = ["pcm_s16le"]
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
