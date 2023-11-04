# playlist manager
import uuid
from typing import List

import click

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
def list_():
    """list all playlists"""
    pl = create_playlist()
    pl.run(pl.list())


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


pl.add_command(list_)
pl.add_command(add)
pl.add_command(remove)
