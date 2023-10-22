def print_table(titles, rows):
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    for k in titles:
        table.add_column(k)
    for row in rows:
        table.add_row(*(str(i) for i in row))
    console.print(table)
