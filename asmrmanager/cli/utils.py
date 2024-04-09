import click

from asmrmanager.logger import logger


@click.group()
def utils(): ...


@click.command()
def migrate():
    from sqlalchemy.sql import text

    from asmrmanager.cli.core import create_database

    db = create_database(skip_check=True)
    if db.check_db_updated():
        logger.error("Database already updated")
        exit(-1)
    db.session.execute(text("ALTER TABLE asmr ADD COLUMN remote_id integer;"))
    db.session.execute(text("UPDATE asmr SET remote_id = id;"))
    db.session.commit()
    logger.info("Database updated successfully")


utils.add_command(migrate)
