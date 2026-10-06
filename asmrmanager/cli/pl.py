import uuid
from collections import Counter
from contextlib import contextmanager
from typing import Literal

import click
from click.shell_completion import CompletionItem
from sqlalchemy.exc import SQLAlchemyError

from asmrmanager.cli.core import (
    create_database,
    fm,
    get_prev_source,
    pl_preprocess_cb,
    save_source,
)
from asmrmanager.common.output import print_table, support_image
from asmrmanager.common.rj_parse import id2source_name
from asmrmanager.common.types import PRIVACY
from asmrmanager.config import config
from asmrmanager.database.database import Playlist


class PLID(click.ParamType):
    name = "pl_id"

    def shell_complete(
        self, ctx: click.Context, param: click.Parameter, incomplete: str
    ) -> list[CompletionItem]:
        try:
            db = create_database()
        except click.ClickException:
            return []
        playlists = db.list_playlists()
        counts = Counter(item.name for item in playlists)
        choices = {str(item.id): item.name for item in playlists}
        choices.update(
            (item.name, item.description)
            for item in playlists
            if counts[item.name] == 1
        )
        for alias, target in config.playlist_aliases.items():
            try:
                playlist = db.get_playlist(target)
            except ValueError:
                continue
            choices[alias] = playlist.name
        return [
            CompletionItem(value, help=description)
            for value, description in choices.items()
            if value.casefold().startswith(incomplete.casefold())
        ]


def _print_playlists(playlists: list[Playlist], raw: bool = False):
    print_table(
        titles=[
            "id",
            "remote_id",
            "name",
            "description",
            "known_members",
            "privacy",
            "members_complete",
        ],
        rows=[
            (
                str(item.id),
                str(item.remote_id) if item.remote_id is not None else None,
                item.name,
                item.description,
                len(item.works),
                PRIVACY(item.privacy).name,
                item.members_complete,
            )
            for item in playlists
        ],
        raw=raw,
    )


@contextmanager
def _playlist_edit():
    if config.sync.playlist:
        raise click.ClickException(
            "Playlist cloud synchronization is not available; "
            "set sync.playlist = false for local-only changes."
        )
    db = create_database()
    try:
        yield db
        db.commit()
    except BaseException as exc:
        db.session.rollback()
        if isinstance(exc, ValueError):
            raise click.ClickException(str(exc)) from exc
        if isinstance(exc, SQLAlchemyError):
            raise click.ClickException(
                "Could not save local playlist changes."
            ) from exc
        raise


@click.group()
def pl():
    """Manage local playlists."""


@click.command("list")
@click.option(
    "--num",
    "-n",
    type=click.IntRange(1),
    default=12,
    show_default=True,
    help="Maximum number of local playlists to show.",
)
@click.option("--raw", "-r", is_flag=True, help="Output JSON.")
def list_(num: int, raw: bool):
    """List local playlists without fetching cloud data."""
    _print_playlists(create_database().list_playlists(num), raw)


@click.command()
@click.argument("pl_id", type=PLID(), callback=pl_preprocess_cb)
@click.argument("source_ids", nargs=-1)
def add(source_ids: tuple[str, ...], pl_id: uuid.UUID):
    """Add works already in the local database to a playlist."""
    sources = source_ids or (get_prev_source(),)
    with _playlist_edit() as db:
        works = [db.resolve_local_work(source) for source in sources]
        db.add_playlist_works(pl_id, [work.id for work in works])
    if len(sources) == 1:
        save_source(sources[0])


@click.command("rm")
@click.argument("pl_ids", type=PLID(), nargs=-1, callback=pl_preprocess_cb)
def remove(pl_ids: list[uuid.UUID]):
    """Delete entire local playlists, keeping their works."""
    with _playlist_edit() as db:
        db.remove_playlists(pl_ids)


@click.command()
@click.argument("name")
@click.option("--desc", "-d", default=None, help="Playlist description.")
@click.option(
    "--privacy",
    "-p",
    type=click.Choice([item.name for item in PRIVACY]),
    default="PRIVATE",
)
def create(
    name: str,
    desc: str | None,
    privacy: Literal["PUBLIC", "NON_PUBLIC", "PRIVATE"],
):
    """Create an unlinked local playlist."""
    with _playlist_edit() as db:
        playlist = db.create_playlist(name, desc, PRIVACY[privacy])
    _print_playlists([playlist])


@click.command()
@click.argument("pl_id", type=PLID(), callback=pl_preprocess_cb)
def show(pl_id: uuid.UUID):
    """Show a local playlist and its known members."""
    playlist = create_database().get_playlist(pl_id)
    _print_playlists([playlist])
    if not playlist.members_complete:
        click.echo(
            "Playlist membership is incomplete; only known local members are shown.",
            err=True,
        )
    works = sorted(playlist.works, key=lambda work: work.id)
    print_table(
        titles=[
            "id",
            "title",
            "circle_name",
            "nsfw",
            "subtitle",
            "dl_count",
            "voice_actors",
        ],
        rows=[
            (
                id2source_name(work.id),
                work.title,
                work.circle_name,
                work.nsfw,
                work.has_subtitle,
                work.dl_count,
                ",".join(actor.name for actor in work.vas),
            )
            for work in works
        ],
        image_paths=(
            [str(fm.get_cover_path(work.id)) for work in works]
            if support_image()
            else None
        ),
    )


pl.add_command(list_)
pl.add_command(add)
pl.add_command(remove)
pl.add_command(create)
pl.add_command(show)
