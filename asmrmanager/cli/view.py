from typing import Literal

import click

from asmrmanager.cli.core import fm, id2source_name, rj_argument
from asmrmanager.common.types import LocalSourceID
from asmrmanager.filemanager.exceptions import SrcNotExistsException
from asmrmanager.logger import logger


@click.group(help="some operation about view_path")
def view():
    pass


@click.command()
@rj_argument("local")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["link", "zip", "adb", "copy"]),
    default="zip",
    show_default=True,
)
def add(source_id: LocalSourceID, mode: Literal["link", "zip", "adb", "copy"]):
    """add an ASMR to view path (use zip by default)"""
    from asmrmanager.cli.core import fm
    from asmrmanager.filemanager.utils import folder_chooser

    src = fm.get_path(source_id)
    if src is None:
        raise SrcNotExistsException

    rj_name = id2source_name(source_id)
    dst = fm.view_path / rj_name
    if dst.exists():
        i = 1
        while True:
            dst = fm.view_path / f"{rj_name}.{i}"
            if not dst.exists():
                break
            i += 1
        logger.warning(f"{rj_name} already exists, use {dst} instead")
        # raise DstItemAlreadyExistsException

    src = folder_chooser(src)

    match mode:
        case "zip":
            fm.zip_file(src, dst)
        case "link":
            fm.link(src, dst)
        case "copy":
            fm._copy(src, dst, depth=1)
        case "adb":
            raise NotImplementedError


@click.command("list")
def list_():
    """list all files in view path"""
    rjs = fm.list_("view")
    print(*rjs, sep="\n")


@click.command()
@rj_argument("local")
def remove(source_id: LocalSourceID):
    """remove a file link in view path"""
    fm.remove_view(source_id)


view.add_command(add)
view.add_command(list_)
view.add_command(remove)
