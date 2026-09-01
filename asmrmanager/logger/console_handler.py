import logging
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape
from rich.text import Text
from rich.traceback import Traceback


def _breakable(char: str) -> bool:
    if char in " \t":
        return True
    return unicodedata.east_asian_width(char) in ("W", "F")


def _wrap(text: Text, width: int) -> list[Text]:
    plain = text.plain
    length = len(plain)
    offsets = []
    offset = 0
    while offset < length:
        i = offset
        cells = 0
        last_break = -1
        while i < length:
            char = plain[i]
            char_width = cell_len(char)
            if cells + char_width > width:
                break
            cells += char_width
            i += 1
            if _breakable(char):
                last_break = i
        if i == length:
            offset = length
            continue
        if last_break > offset and _segment_fits(plain, last_break, width):
            end = last_break
        else:
            end = i if i > offset else offset + 1
        offsets.append(end)
        offset = end
    lines = text.divide(offsets)
    for line in lines:
        line.rstrip()
    return list(lines)


def _segment_fits(plain: str, start: int, width: int) -> bool:
    end = start
    while end < len(plain) and plain[end] not in " \t":
        end += 1
    return cell_len(plain[start:end]) <= width


class RichLogHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET, console=None):
        super().__init__(level=level)
        self.console = console or Console(stderr=True, highlight=False)

    def emit(self, record):
        try:
            self.console.print(
                self.render_line(record), no_wrap=True, overflow="ignore", crop=False
            )
            if record.exc_info and record.exc_info[0]:
                self.console.print(Traceback.from_exception(*record.exc_info))
        except Exception:
            self.handleError(record)

    def render_line(self, record):
        time_text = (
            datetime.fromtimestamp(record.created, UTC)
            .astimezone()
            .strftime("[%X] ")
        )
        level_text = record.levelname.ljust(8)
        prefix_width = len(time_text) + len(level_text) + 1
        lines = _wrap(
            self.render_message(record),
            max(self.console.width - prefix_width, 10),
        )
        line = Text()
        line.append_text(Text(time_text, style="log.time"))
        line.append_text(
            Text.styled(level_text, f"logging.level.{record.levelname.lower()}")
        )
        line.append_text(Text(" "))
        line.append_text(lines[0])
        indent = Text(" " * prefix_width)
        for extra in lines[1:]:
            line.append_text(Text("\n"))
            line.append_text(indent)
            line.append_text(extra)
        return line

    @staticmethod
    def render_message(record):
        msg = record.msg
        args = record.args
        if not args:
            return Text.from_markup(msg if isinstance(msg, str) else str(msg))
        if not isinstance(args, tuple):
            args = (args,)
        new_args = tuple(
            RichLogHandler.path_markup(arg) if isinstance(arg, Path) else arg
            for arg in args
        )
        try:
            text = msg % new_args
        except (TypeError, ValueError):
            text = record.getMessage()
        return Text.from_markup(text)

    @staticmethod
    def path_markup(path: Path) -> str:
        url = "file://" + quote(str(path.absolute()))
        return f"[link={url}][bold blue]{escape(str(path))}[/bold blue][/link]"
