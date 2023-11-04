# playlist manager
import uuid
from typing import List

import click
from typing_extensions import Literal

from asmrmanager.cli.core import (
    create_playlist,
    multi_rj_argument,
    pl_preprocess_cb,
)
from asmrmanager.common.rj_parse import RJID


@click.group()
def pl():
    """asmr playlist interface"""


@click.command("list")
@click.option(
    "--num",
    "-n",
    default=12,
    show_default=True,
    help="number of playlists to show",
)
@click.option(
    "--raw",
    "-r",
    is_flag=True,
    default=False,
    show_default=True,
    help="raw output",
)
def list_(num: int, raw: bool):
    """list all playlists"""
    pl = create_playlist()
    pl.run(pl.list(num, raw))


@click.command()
@multi_rj_argument
@click.argument("pl_id", callback=pl_preprocess_cb)
def add(rj_ids: List[RJID], pl_id: uuid.UUID):
    """add a playlist"""
    pl = create_playlist()
    pl.run(pl.add(rj_ids, pl_id))


@click.command("rm")
@click.argument("pl_ids", nargs=-1, callback=pl_preprocess_cb)
def remove(pl_ids: List[uuid.UUID]):
    """remove a playlist"""
    pl = create_playlist()
    pl.run(pl.remove(pl_ids))


@click.command()
@click.argument("name")
@click.option("--desc", "-d", default=None, help="playlist description")
@click.option(
    "--privacy",
    "-p",
    type=click.Choice(["PUBLIC", "NON_PUBLIC", "PRIVATE"]),
    default="PRIVATE",
)
def create(
    name: str,
    desc: str | None,
    privacy: Literal["PUBLIC", "NON_PUBLIC", "PRIVATE"],
):
    """create a playlist"""
    pl = create_playlist()
    pl.run(pl.create(name, desc, privacy))


pl.add_command(list_)
pl.add_command(add)
pl.add_command(remove)
pl.add_command(create)
