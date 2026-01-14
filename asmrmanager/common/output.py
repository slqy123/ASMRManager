from functools import cache


@cache
def support_image():
    from asmrmanager.config import config

    if not (config.fetch_cover and config.display_cover):
        return False

    from importlib.util import find_spec

    if not find_spec("textual_image"):
        return False

    from textual_image.renderable import HalfcellImage, Image, UnicodeImage

    if Image in (HalfcellImage, UnicodeImage):
        return False
    return True


def _print_table(
    titles, rows, raw=False, image_index: int | None = None, image_size=(8, 3)
):
    from rich.console import Console
    from rich.table import Table

    if raw:
        import json

        res_json = json.dumps(
            [{k: v for k, v in zip(titles, item)} for item in rows],
            ensure_ascii=False,
        )
        import click

        click.echo(res_json)
        return

    if image_index is not None and support_image():
        from textual_image.renderable import Image

        row_mapper = lambda row: (
            Image(r, width=image_size[0], height=image_size[1])
            if i == image_index
            else str(r)
            for i, r in enumerate(row)
        )
    else:
        row_mapper = lambda row: (str(r) for r in row)

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    for k in titles:
        table.add_column(k, overflow="fold")
    for row in rows:
        table.add_row(*row_mapper(row))
    console.print(table)


def print_table(
    titles,
    rows,
    raw=False,
    image_paths: list[str] | None = None,
    image_size=(8, 3),
):
    if raw or not support_image():
        _print_table(titles, rows, raw)
        return

    if image_paths:
        _print_table(
            ("cover", *titles),
            [(image_paths[i], *row) for i, row in enumerate(rows)],
            raw,
            image_index=0,
            image_size=image_size,
        )
    else:
        _print_table(titles, rows, raw)
