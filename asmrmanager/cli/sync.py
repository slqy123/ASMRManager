import json
import sys
import uuid
from dataclasses import dataclass

import click

from asmrmanager.cli.core import (
    create_database,
    create_sync_api,
    push_local_review,
    rj_argument,
)
from asmrmanager.common.types import PRIVACY, LocalSourceID
from asmrmanager.config import config
from asmrmanager.database.database import ASMR, Playlist
from asmrmanager.sync import SyncError, review_values


def enabled_review_fields():
    return [
        name
        for name in ("star", "comment", "progress")
        if getattr(config.sync, name)
    ]


@click.group()
def sync():
    """Explicitly push local reviews or pull cloud changes."""


@sync.command()
@rj_argument("local-only")
@click.option(
    "--field",
    "fields",
    multiple=True,
    type=click.Choice(("star", "comment", "progress")),
    help="Retry only these enabled fields; default: all enabled review fields.",
)
def push(source_id: LocalSourceID, fields):
    """Retry current local review values without changing dates or files."""
    enabled = enabled_review_fields()
    if fields and not set(fields) <= set(enabled):
        raise click.ClickException(
            "Requested review fields must be enabled in [sync]."
        )
    selected = list(dict.fromkeys(fields)) if fields else enabled
    if not selected:
        raise click.ClickException(
            "No review synchronization fields are enabled."
        )
    work = create_database().resolve_local_work(str(source_id))
    try:
        push_local_review(work, selected)
    except SyncError as exc:
        raise click.ClickException(
            f"Local review values were kept. {exc}"
        ) from None
    click.echo(
        "Current local review values were synchronized; dates and files were not changed."
    )


@dataclass
class Difference:
    kind: str
    key: int | uuid.UUID
    field: str
    before: object
    after: object
    missing: bool = False


def differences(db, snapshot, fields, playlist_enabled):
    result = []
    unchanged = 0
    local_works = {work.id: work for work in db.session.query(ASMR)}
    for key in (
        sorted(set(local_works) | set(snapshot.reviews)) if fields else ()
    ):
        row = snapshot.reviews.get(key)
        values = (
            review_values(row)
            if row is not None
            else {"star": 0, "comment": "", "progress": None}
        )
        work = local_works.get(key)
        if work is None:
            result.append(
                Difference(
                    "work",
                    key,
                    "new work",
                    None,
                    {field: values[field] for field in fields},
                )
            )
            continue
        for field in fields:
            before = getattr(work, field)
            if field == "star" and before is None:
                before = 0
            if field == "comment" and before is None:
                before = ""
            if before == values[field]:
                unchanged += 1
            else:
                result.append(
                    Difference(
                        "review",
                        key,
                        field,
                        before,
                        values[field],
                        missing=row is None,
                    )
                )
    if playlist_enabled:
        linked = {
            item.remote_id: item
            for item in db.list_playlists()
            if item.remote_id is not None
        }
        for remote_id in sorted(
            set(linked) | set(snapshot.playlists), key=str
        ):
            local = linked.get(remote_id)
            remote = snapshot.playlists.get(remote_id)
            if remote is None:
                result.append(
                    Difference(
                        "deleteplaylist",
                        remote_id,
                        "cloud playlist missing",
                        local.name,
                        None,
                    )
                )
                continue
            metadata = remote.metadata
            after = {
                "name": metadata["name"],
                "description": metadata["description"],
                "privacy": metadata["privacy"],
                "members": sorted(remote.works),
            }
            before = (
                None
                if local is None
                else {
                    "name": local.name,
                    "description": local.description,
                    "privacy": local.privacy,
                    "members": sorted(work.id for work in local.works),
                }
            )
            if before == after:
                unchanged += 1
            else:
                result.append(
                    Difference(
                        "playlist",
                        remote_id,
                        "playlist metadata/members",
                        before,
                        after,
                    )
                )
    return result, unchanged


def apply_difference(db, snapshot, manager, change):
    def work(local_id):
        existing = db.session.get(ASMR, local_id)
        if existing is None:
            db.add_info(
                snapshot.works[local_id],
                check=False,
                tag_strategy=config.tag_strategy,
            )
            existing = db.session.get(ASMR, local_id)
        info = snapshot.works.get(local_id)
        if info is not None and existing.remote_id is not None and existing.remote_id != info["id"]:
            raise SyncError("Conflicting cloud work mapping; nothing was applied.")
        return existing

    if change.kind == "work":
        item = work(change.key)
        for name, value in change.after.items():
            setattr(item, name, value)
    elif change.kind == "review":
        setattr(work(change.key), change.field, change.after)
    else:
        item = (
            db.session.query(Playlist)
            .filter_by(remote_id=change.key)
            .one_or_none()
        )
        if item is not None:
            manager.binding(item)
        if change.kind == "deleteplaylist":
            db.session.delete(item)
        else:
            remote = snapshot.playlists[change.key]
            if item is None:
                item = db.create_playlist(
                    remote.metadata["name"],
                    remote.metadata["description"],
                    PRIVACY(remote.metadata["privacy"]),
                )
                item.remote_id = change.key
                item.remote_service, item.remote_user = (
                    manager.service,
                    manager.user,
                )
            item.name, item.description, item.privacy = (
                remote.metadata[name]
                for name in ("name", "description", "privacy")
            )
            item.works = [work(local_id) for local_id in sorted(remote.works)]


@sync.command()
@click.option(
    "--choice",
    type=click.Choice(("ask", "cloud", "local")),
    default="ask",
    show_default=True,
    help="Explicit decision for all differences; ask skips conflicts without a terminal.",
)
@click.option(
    "--interactive/--no-interactive",
    default=None,
    help="Override terminal detection for conflict prompts.",
)
def pull(choice, interactive):
    """Pull enabled types; differences require an explicit decision."""
    fields = enabled_review_fields()
    if not fields and not config.sync.playlist:
        click.echo(
            "No synchronization types are enabled; no cloud request was made."
        )
        return
    db = create_database()
    try:
        manager = create_sync_api()
        snapshot = manager.run(
            manager.snapshot(
                bool(fields),
                config.sync.playlist,
                {work.id for work in db.session.query(ASMR)},
            )
        )[0]
        if config.sync.playlist:
            for playlist in db.list_playlists():
                if playlist.remote_id is not None:
                    manager.binding(playlist)
        changes, unchanged = differences(
            db, snapshot, fields, config.sync.playlist
        )
    except SyncError as exc:
        raise click.ClickException(f"Nothing was applied. {exc}") from None
    interactive = sys.stdin.isatty() if interactive is None else interactive
    decision = choice
    applied = skipped = failed = unresolved = 0
    for change in changes:
        current = decision
        label = change.field + (
            " (cloud review missing)" if change.missing else ""
        )
        if current == "ask" and interactive:
            click.echo(
                f"{change.key} {label}: {json.dumps(change.before, ensure_ascii=False)} -> {json.dumps(change.after, ensure_ascii=False)}"
            )
            current = click.prompt(
                "Choose",
                type=click.Choice(
                    ("cloud", "local", "cloud-all", "local-all")
                ),
                default="local",
            )
            if current.endswith("-all"):
                current = current.removesuffix("-all")
                decision = current
        if current != "cloud":
            skipped += 1
            if current == "ask":
                unresolved += 1
                click.echo(
                    f"Unresolved difference: {change.key} {label}.", err=True
                )
            continue
        try:
            apply_difference(db, snapshot, manager, change)
            db.commit()
            applied += 1
        except Exception:
            db.session.rollback()
            failed += 1
            click.echo(
                f"Could not apply cloud difference for {change.key}; local changes were rolled back.",
                err=True,
            )
    click.echo(
        f"Pull: applied={applied}, unchanged={unchanged}, skipped={skipped}, failed={failed}, conflicts={len(changes)}, unresolved={unresolved}."
    )
    if failed or unresolved:
        raise click.ClickException(
            "Pull has failed or unresolved differences; no reverse push was made."
        )
