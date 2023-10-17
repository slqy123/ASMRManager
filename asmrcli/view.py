from typing import Literal

import click

from asmrcli.core import rj_argument
from common.rj_parse import RJID, id2rj


@click.group(help="some operation about view_path")
def view():
    pass


@click.command()
@rj_argument
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["link", "zip", "adb"]),
    default="zip",
    show_default=True,
)
def add(rj_id: RJID, mode: Literal["link", "zip", "adb"]):
    """add an ASMR to view path (use zip by default)"""
    from asmrcli.core import create_fm

    fm = create_fm()

    match mode:
        case "zip":
            fm.zip_file(rj_id)
        case "link":
            fm.view(rj_id, replace=True)
        case "adb":
            raise NotImplementedError


@click.command("list")
def list_():
    """list all files in view path"""
    from asmrcli.core import create_fm

    fm = create_fm()
    rjs = fm.list_("view")
    print(*rjs, sep="\n")


@click.command()
@rj_argument
def remove(rj_id: RJID):
    """remove a file link in view path"""
    from asmrcli.core import create_fm

    fm = create_fm()
    fm.remove_view(rj_id)


view.add_command(add)
view.add_command(list_)
view.add_command(remove)
