from datetime import datetime, timedelta
from pathlib import Path
from asmrmanager.logger import logger

import click


def parse_time(time_str):
    dt = datetime.strptime(time_str.strip(), "%H:%M:%S.%f")
    return dt


def format_time(time):
    return time.strftime("%M:%S.%f")[:8]


DEFAULT_THRESHOLD = timedelta(seconds=2)


def vtt2lrc(vtt_path: Path, header=True, threshold=DEFAULT_THRESHOLD):
    print(vtt_path)
    lrc = ""

    if header:
        lrc += "[re:vtt2lrc]\n"

    last_end = parse_time("23:59:59.99")  # Insanely big value

    vtt = vtt_path.read_text(encoding="utf-8")
    for chunk in vtt.split("\n\n")[1:]:
        if not chunk:
            continue

        # res = chunk.strip().split("\n", 1)
        # if res[0].isdigit():
        #     time, text = res[1].split("\n", 1)
        # else:
        #     time, text = res

        match chunk.strip().split("\n"):
            case [index, time, *text] if index.isdigit() and "-->" in time:
                text = "\n".join(text)
            case _:
                logger.warning(
                    f"Invalid chunk in vtt file {vtt_path}:\n{chunk}"
                )
                continue

        begin, end = map(parse_time, time.split("-->"))

        if begin - last_end > threshold:
            lrc += f"[{format_time(last_end)}]\n"

        lrc += f"[{format_time(begin)}] {text}\n"

        last_end = end

    lrc += f"[{format_time(last_end)}]\n"

    return lrc


@click.command()
@click.argument(
    "vtt", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def main(vtt: Path):
    lrc = vtt2lrc(vtt)
    with open(
        vtt.with_suffix("").with_suffix(".lrc"), "w", encoding="utf-8"
    ) as f:
        f.write(lrc)
