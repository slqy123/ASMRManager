import click
from sqlalchemy.exc import SQLAlchemyError

from asmrmanager.cli.core import create_database, fm, rj_argument
from asmrmanager.common.types import PROGRESS_VALUES, LocalSourceID
from asmrmanager.config import config
from asmrmanager.logger import logger


@click.command()
@rj_argument("local-only")
@click.option(
    "-s", "--star", type=click.IntRange(0, 5), help="Rating; 0 clears it."
)
@click.option(
    "-c", "--comment", type=str, help="Replace the comment; '' clears it."
)
@click.option("--progress", type=click.Choice(PROGRESS_VALUES))
@click.option(
    "--clear-progress", is_flag=True, help="Clear the listening status."
)
def review(
    source_id: LocalSourceID,
    star: int | None,
    comment: str | None,
    progress: str | None,
    clear_progress: bool,
):
    """Set a work's current rating, comment or listening status."""
    if (
        star is None
        and comment is None
        and progress is None
        and not clear_progress
    ):
        raise click.UsageError(
            "Specify a rating, comment or listening status."
        )
    db = create_database()
    try:
        asmr = db.update_review(
            source_id,
            star,
            comment,
            progress=progress,
            clear_progress=clear_progress,
        )
        if star is not None or comment is not None:
            if fm.could_store() and fm.get_location(source_id) is not None:
                fm.store(source_id)
                asmr.stored = fm.get_location(source_id) == "storage"
            else:
                logger.warning(
                    "No local files or storage path; skipping file storage"
                )
        db.commit()
    except BaseException as exc:
        db.session.rollback()
        if isinstance(exc, ValueError):
            raise click.ClickException(str(exc)) from exc
        if isinstance(exc, SQLAlchemyError):
            raise click.ClickException(
                "Could not save local review changes."
            ) from None
        raise
    sync_fields = [
        field
        for field, submitted in (
            ("star", star is not None),
            ("comment", comment is not None),
            ("progress", progress is not None or clear_progress),
        )
        if submitted and getattr(config.sync, field)
    ]
    if sync_fields:
        raise click.ClickException(
            "Local review changes were saved, but cloud synchronization "
            f"is not available for: {', '.join(sync_fields)}. "
            "No cloud request was made."
        )
