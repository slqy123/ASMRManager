import os
from subprocess import run

import click
from click.shell_completion import CompletionItem

from asmrmanager.cli.core import fm
from asmrmanager.common.output import print_table
from asmrmanager.config import config
from asmrmanager.logger import logger


class SQLName(click.ParamType):
    name = "sql_name"

    def shell_complete(
        self, ctx: click.Context, param: click.Parameter, incomplete: str
    ):
        return [
            CompletionItem(name)
            for name in os.listdir(fm.DATA_PATH / "sqls")
            if name.upper().startswith(incomplete.upper())
        ]


@click.command()
@click.argument("sql_name", type=SQLName())
@click.option(
    "--save/--no-save",
    "-s/-ns",
    is_flag=True,
    default=True,
    help="should your change to the file be saved",
)
def sql(sql_name: str, save: bool):
    """
    execute a sql statement by sql file name in `sqls` directory
    and print the results on your terminal
    """
    sql_path = fm.DATA_PATH / "sqls" / sql_name
    sql_path = sql_path.with_suffix(".sql")
    if not sql_path.exists():
        logger.error(
            f"cannot locate sql {sql_name}, "
            "check ./sqls for possible sql scripts"
        )
        return

    fm.CACHE_PATH.mkdir(parents=True, exist_ok=True)
    temp_file_path = fm.CACHE_PATH / "tempfile.sql"
    temp_file_path.write_text(
        sql_path.read_text(encoding="utf8"), encoding="utf8"
    )
    run(f'{config.editor} "{temp_file_path}"', shell=True)
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
    from asmrmanager.cli.core import create_database

    db = create_database()
    res = db.execute(temp_file_path.read_text(encoding="utf8"))
    rows = res.fetchall()
    titles = res.keys()
    print_table(titles, rows)

    if save:
        sql_path.write_text(
            temp_file_path.read_text(encoding="utf8"), encoding="utf8"
        )
    os.remove(temp_file_path)
