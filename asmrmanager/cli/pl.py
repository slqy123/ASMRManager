import uuid
from collections import Counter
from contextlib import contextmanager
from typing import Literal

import click
from click.shell_completion import CompletionItem
from sqlalchemy.exc import SQLAlchemyError

from asmrmanager.cli.core import (
    create_database,
    create_sync_api,
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
from asmrmanager.sync import PlaylistBinding, SyncError


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
def _playlist_edit(cloud_id=None):
    db = create_database()
    try:
        yield db
        db.commit()
    except BaseException as exc:
        db.session.rollback()
        if isinstance(exc, ValueError):
            raise click.ClickException(str(exc)) from exc
        if isinstance(exc, SQLAlchemyError):
            message = "Could not save local playlist changes."
            if cloud_id is not None:
                message += f" Cloud operation succeeded for {cloud_id}; inspect or link that ID before retrying, and use sync pull to reconcile."
            raise click.ClickException(message) from None
        raise


def _linked(playlist):
    if playlist.remote_id is None:
        raise click.ClickException(
            "Playlist is not linked; use asmr pl publish or asmr pl link first."
        )


def _sync_enabled():
    if not config.sync.playlist:
        raise click.ClickException(
            "Enable sync.playlist before publishing or linking; no cloud request was made."
        )


def _publish(name, description, privacy, works):
    manager = create_sync_api()
    created = manager.run(
        manager.publish(
            name,
            description,
            privacy,
            [(work.id, work.remote_id) for work in works],
        )
    )[0]
    return manager, created


def _bind(playlist, manager, remote_id):
    playlist.remote_id = remote_id
    playlist.remote_service, playlist.remote_user = (
        manager.service,
        manager.user,
    )


def _verify_publication(playlist, manager, local_ids):
    remote_id = playlist.remote_id
    try:
        manager.run(manager.verify_publication(remote_id, local_ids))
    except SyncError:
        raise click.ClickException(
            f"Cloud playlist {remote_id} was created and linked, but member verification failed. Use sync pull; do not publish again."
        ) from None
    with _playlist_edit(remote_id):
        playlist.members_complete = True


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
    db = create_database()
    playlist = db.get_playlist(pl_id)
    with _playlist_edit(
        playlist.remote_id if config.sync.playlist else None
    ) as db:
        works = [db.resolve_local_work(source) for source in sources]
        if config.sync.playlist:
            _linked(playlist)
            manager = create_sync_api()
            manager.run(
                manager.add(
                    PlaylistBinding.from_playlist(playlist),
                    [(work.id, work.remote_id) for work in works],
                )
            )
        db.add_playlist_works(pl_id, [work.id for work in works])
    if len(sources) == 1:
        save_source(sources[0])


@click.command("rm")
@click.argument("pl_ids", type=PLID(), nargs=-1, callback=pl_preprocess_cb)
def remove(pl_ids: list[uuid.UUID]):
    """Delete entire local playlists, keeping their works."""
    db = create_database()
    playlists = [
        db.get_playlist(identifier) for identifier in dict.fromkeys(pl_ids)
    ]
    if config.sync.playlist:
        for playlist in playlists:
            _linked(playlist)
        manager = create_sync_api()
        manager.run(
            manager.remove(
                [
                    PlaylistBinding.from_playlist(playlist)
                    for playlist in playlists
                ]
            )
        )
    with _playlist_edit(
        ", ".join(str(item.remote_id) for item in playlists)
        if config.sync.playlist
        else None
    ) as db:
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
    """Create locally, or create and link a cloud playlist when enabled."""
    if not name.strip():
        raise click.ClickException("Playlist name must not be empty.")
    manager = created = None
    if config.sync.playlist:
        manager, created = _publish(
            name, desc or "", PRIVACY[privacy].value, []
        )
    remote_id = uuid.UUID(created["id"]) if created else None
    with _playlist_edit(remote_id) as db:
        playlist = db.create_playlist(name, desc, PRIVACY[privacy])
        if manager is not None:
            _bind(playlist, manager, remote_id)
            playlist.members_complete = False
    if manager is not None:
        _verify_publication(playlist, manager, [])
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


@click.command()
@click.argument("pl_id", type=PLID(), callback=pl_preprocess_cb)
def publish(pl_id):
    """Publish a complete unlinked local playlist and save its cloud ID."""
    _sync_enabled()
    playlist = create_database().get_playlist(pl_id)
    if playlist.remote_id is not None:
        raise click.ClickException(
            "Playlist is already linked; use sync pull instead of publishing again."
        )
    if not playlist.members_complete:
        raise click.ClickException(
            "Playlist membership is incomplete; cannot publish unknown members."
        )
    local_ids = [work.id for work in playlist.works]
    manager, created = _publish(
        playlist.name, playlist.description, playlist.privacy, playlist.works
    )
    remote_id = uuid.UUID(created["id"])
    with _playlist_edit(remote_id):
        _bind(playlist, manager, remote_id)
        playlist.members_complete = False
    _verify_publication(playlist, manager, local_ids)
    _print_playlists([playlist])


@click.command()
@click.argument("pl_id", type=PLID(), callback=pl_preprocess_cb)
@click.argument("remote_id", type=click.UUID)
def link(pl_id, remote_id):
    """Link an explicitly chosen owned cloud ID without replacing members."""
    _sync_enabled()
    playlist = create_database().get_playlist(pl_id)
    if playlist.remote_id is not None and playlist.remote_id != remote_id:
        raise click.ClickException(
            "Playlist is already linked to another cloud ID."
        )
    manager = create_sync_api()
    manager.run(manager.link(remote_id))
    if playlist.remote_id is not None and playlist.remote_service is not None:
        manager.binding(playlist)
        click.echo(
            "Playlist is already linked to this service, account and ID."
        )
        return
    with _playlist_edit() as db:
        if (
            db.session.query(Playlist)
            .filter(Playlist.remote_id == remote_id, Playlist.id != pl_id)
            .first()
            is not None
        ):
            raise ValueError(
                "Cloud ID is already linked to another local playlist."
            )
        _bind(playlist, manager, remote_id)
        playlist.members_complete = False
    _print_playlists([playlist])


pl.add_command(publish)
pl.add_command(link)
pl.add_command(list_)
pl.add_command(add)
pl.add_command(remove)
pl.add_command(create)
pl.add_command(show)
