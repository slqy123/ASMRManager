import click
from asmrcli.core import create_database

@click.command()
@click.option('-s', '--subtitle', type=bool, default=None)
@click.option('-n', '--nsfw', type=bool, default=None)
def query(subtitle: bool):
    db = create_database()
    print(subtitle)
