import click

from asmrmanager.cli.core import rj_argument
from asmrmanager.common.types import LocalSourceID


@click.command()
@rj_argument("local")
@click.option("-c", "--comment", type=str, default=None, show_default=True)
def hold(source_id: LocalSourceID, comment: str | None = None):
    """Hold a work and save the reason as a local note."""

    from asmrmanager.cli.core import create_database

    db = create_database()
    db.hold_item(source_id, comment)
    db.commit()
