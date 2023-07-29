import click
from pathlib import Path

from logger import logger
from subprocess import run
from config import config
import os


@click.command()
@click.argument('sql_name', type=str)
@click.option(
    '--save/--no-save',
    '-s/-ns',
    is_flag=True,
    default=True,
    help='should your change to the file be saved',
)
def sql(sql_name: str, save: bool = False):
    """
    execute a sql statement by sql file name in `sqls` directory
    and print the results on your terminal
    """
    sql_path = Path(__file__).parent.parent / 'sqls' / sql_name
    sql_path = sql_path.with_suffix('.sql')
    if not sql_path.exists():
        logger.error(
            f'cannot locate sql {sql_name}, '
            'check ./sqls for possible sql scripts'
        )
        return

    temp_file_path = sql_path.parent.parent / 'tempfile.sql'
    temp_file_path.write_text(
        sql_path.read_text(encoding='utf8'), encoding='utf8'
    )
    run(f'{config.editor} {temp_file_path}')
    # db_path = temp_file_path.with_name('data.db')
    # print(db_path, temp_file_path)
    # run(
    #     [
    #         'litecli',
    #         str(db_path),
    #         '-e',
    #         temp_file_path.read_text(encoding='utf8'),
    #     ]
    # )
    from asmrcli.core import create_database

    db = create_database()
    res = db.execute(temp_file_path.read_text(encoding='utf8'))
    rows = res.fetchall()
    titles = res.keys()
    print_table(titles, rows)

    if save:
        sql_path.write_text(
            temp_file_path.read_text(encoding='utf8'), encoding='utf8'
        )
    os.remove(temp_file_path)


def print_table(titles, rows):
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(show_header=True, header_style='bold magenta')
    for k in titles:
        table.add_column(k)
    for row in rows:
        table.add_row(*(str(i) for i in row))
    console.print(table)
