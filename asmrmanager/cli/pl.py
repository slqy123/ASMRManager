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
from asmrmanager.database.database import ASMR, Playlist
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
            "members",
            "privacy",
        ],
        rows=[
            (
                str(item.id),
                str(item.remote_id) if item.remote_id is not None else None,
                item.name,
                item.description,
                len(item.works),
                PRIVACY(item.privacy).name,
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
                message += f" Cloud operation succeeded for {cloud_id}; inspect or bind that ID before retrying, and use pl pull to reconcile."
            raise click.ClickException(message) from None
        raise


def _linked(playlist):
    if playlist.remote_id is None:
        raise click.ClickException(
            "Playlist is not bound; use asmr pl push or asmr pl bind first."
        )


def _sync_enabled():
    if not config.sync.playlist:
        raise click.ClickException(
            "Enable sync.playlist first; no cloud request was made."
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
            f"Cloud playlist {remote_id} was created and linked, but member verification failed. Use pl pull; do not create it again."
        ) from None


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
def add(source_ids: tuple[str, ...], pl_id: int):
    """Add works already in the local database to a playlist."""
    sources = source_ids or (get_prev_source(),)
    with _playlist_edit() as db:
        works = [db.resolve_local_work(source) for source in sources]
        db.add_playlist_works(pl_id, [work.id for work in works])
    if len(sources) == 1:
        save_source(sources[0])


@click.command("rm")
@click.argument("pl_ids", type=PLID(), nargs=-1, callback=pl_preprocess_cb)
@click.option(
    "--remote", is_flag=True, help="Also delete the bound cloud playlists."
)
@click.option("--yes", "-y", is_flag=True, help="Confirm cloud deletion.")
def remove(pl_ids: list[int], remote: bool, yes: bool):
    """Delete entire local playlists, keeping their works."""
    db = create_database()
    playlists = [
        db.get_playlist(identifier) for identifier in dict.fromkeys(pl_ids)
    ]
    if remote:
        _sync_enabled()
        for playlist in playlists:
            _linked(playlist)
        if not yes:
            click.confirm(
                "Delete these playlists locally AND in the cloud?", abort=True
            )
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
        if remote
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
    """Create a local playlist without contacting the cloud."""
    with _playlist_edit() as db:
        playlist = db.create_playlist(name, desc, PRIVACY[privacy])
    _print_playlists([playlist])


@click.command()
@click.argument("pl_id", type=PLID(), callback=pl_preprocess_cb)
def show(pl_id: int):
    """Show a local playlist and its members."""
    playlist = create_database().get_playlist(pl_id)
    _print_playlists([playlist])
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
@click.option(
    "--yes", "-y", is_flag=True, help="Confirm cloud creation or replacement."
)
def push(pl_id, yes):
    """Create or update the bound cloud playlist from local data."""
    _sync_enabled()
    playlist = create_database().get_playlist(pl_id)
    local_ids = [work.id for work in playlist.works]
    if playlist.remote_id is not None:
        manager = create_sync_api()
        manager.binding(playlist)
        before = manager.run(manager.playlist(playlist.remote_id))[0]
        metadata = {
            key: getattr(playlist, key)
            for key in ("name", "description", "privacy")
        }
        click.echo(
            f"Cloud {playlist.remote_id}: add={len(set(local_ids) - before.works.keys())}, remove={len(before.works.keys() - set(local_ids))}."
        )
        for key, value in metadata.items():
            if before.metadata[key] != value:
                click.echo(f"{key}: {before.metadata[key]!r} -> {value!r}")
        if not yes:
            click.confirm("Replace cloud data with local data?", abort=True)
        manager.run(
            manager.push(
                PlaylistBinding.from_playlist(playlist),
                before,
                metadata,
                [(work.id, work.remote_id) for work in playlist.works],
            )
        )
    else:
        click.echo(
            f"Create cloud playlist {playlist.name!r} with {len(local_ids)} members."
        )
        if not yes:
            click.confirm("Create and bind this cloud playlist?", abort=True)
        manager, created = _publish(
            playlist.name,
            playlist.description,
            playlist.privacy,
            playlist.works,
        )
        remote_id = uuid.UUID(created["id"])
        with _playlist_edit(remote_id):
            _bind(playlist, manager, remote_id)
        _verify_publication(playlist, manager, local_ids)
    _print_playlists([playlist])


@click.command()
@click.argument("pl_id", type=PLID(), callback=pl_preprocess_cb)
@click.argument("remote_id", type=click.UUID)
def bind(pl_id, remote_id):
    """Bind an owned cloud ID without replacing local metadata or members."""
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
    _print_playlists([playlist])


@click.command()
@click.argument(
    "pl_id", required=False, type=PLID(), callback=pl_preprocess_cb
)
@click.option(
    "--remote",
    "remote_id",
    type=click.UUID,
    help="Import an owned cloud playlist by ID.",
)
@click.option(
    "--yes", "-y", is_flag=True, help="Confirm replacing local data."
)
def pull(pl_id, remote_id, yes):
    """Import or replace a local playlist from the cloud."""
    from asmrmanager.cli.sync import apply_difference, differences

    _sync_enabled()
    if (pl_id is None) == (remote_id is None):
        raise click.UsageError(
            "Specify either a local playlist or --remote, not both."
        )
    db = create_database()
    manager = create_sync_api()
    if pl_id is not None:
        item = db.get_playlist(pl_id)
        _linked(item)
        manager.binding(item)
        remote_id = item.remote_id
    else:
        item = (
            db.session.query(Playlist)
            .filter_by(remote_id=remote_id)
            .one_or_none()
        )
        if item is not None:
            manager.binding(item)
    snapshot = manager.run(
        manager.snapshot(
            False,
            True,
            {work.id for work in db.session.query(ASMR)},
            playlist_ids=[remote_id],
        )
    )[0]
    changes, _ = differences(db, snapshot, (), True)
    change = next(
        (change for change in changes if change.key == remote_id), None
    )
    if change is None:
        click.echo("Playlist is already up to date.")
        return
    click.echo(f"Local {remote_id}: {change.before!r} -> {change.after!r}")
    if not yes:
        click.confirm("Apply this cloud playlist locally?", abort=True)
    with _playlist_edit():
        apply_difference(db, snapshot, manager, change)
    _print_playlists(
        [db.session.query(Playlist).filter_by(remote_id=remote_id).one()]
    )


pl.add_command(pull)
pl.add_command(push)
pl.add_command(bind)
pl.add_command(list_)
pl.add_command(add)
pl.add_command(remove)
pl.add_command(create)
pl.add_command(show)
