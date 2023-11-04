def print_table(titles, rows, raw=False):
    from rich.console import Console
    from rich.table import Table

    if not raw:
        console = Console()
        table = Table(show_header=True, header_style="bold magenta")
        for k in titles:
            table.add_column(k)
        for row in rows:
            table.add_row(*(str(i) for i in row))
        console.print(table)

    else:
        import json

        res_json = json.dumps(
            [{k: v for k, v in zip(titles, item)} for item in rows],
            ensure_ascii=False,
        )
        import click

        click.echo(res_json)
