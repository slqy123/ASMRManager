from typing import Literal

import click

from asmrmanager.cli.core import fm, id2rj, rj_argument
from asmrmanager.common.rj_parse import RJID
from asmrmanager.filemanager.exceptions import (
    DstItemAlreadyExistsException,
    SrcNotExistsException,
)


@click.group(help="some operation about view_path")
def view():
    pass


@click.command()
@rj_argument
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["link", "zip", "adb", "copy"]),
    default="zip",
    show_default=True,
)
def add(rj_id: RJID, mode: Literal["link", "zip", "adb", "copy"]):
    """add an ASMR to view path (use zip by default)"""
    from asmrmanager.cli.core import fm
    from asmrmanager.filemanager.utils import folder_chooser

    src = fm.get_path(rj_id)
    if src is None:
        raise SrcNotExistsException

    rj_name = id2rj(rj_id)
    dst = fm.view_path / rj_name
    if dst.exists():
        raise DstItemAlreadyExistsException

    src = folder_chooser(src)

    match mode:
        case "zip":
            fm.zip_file(src, dst)
        case "link":
            fm.link(src, dst)
        case "copy":
            fm._copy(src, dst)
        case "adb":
            raise NotImplementedError


@click.command("list")
def list_():
    """list all files in view path"""
    rjs = fm.list_("view")
    print(*rjs, sep="\n")


@click.command()
@rj_argument
def remove(rj_id: RJID):
    """remove a file link in view path"""
    fm.remove_view(rj_id)


view.add_command(add)
view.add_command(list_)
view.add_command(remove)
