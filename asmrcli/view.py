import click
from asmrcli.core import rj_argument

@click.group()
def view():
    pass


@click.command()
@rj_argument
def add(rj_id: int):
    from asmrcli.core import id2rj, create_fm
    rj = id2rj(rj_id)
    fm = create_fm()

    if fm.could_view():
        fm.view(rj, replace=True)


@click.command('list')
def list_():
    from asmrcli.core import create_fm

    fm = create_fm()
    rjs = fm.list_('view')
    print(*rjs, sep='\n')

@click.command()
def search():
    pass

view.add_command(add)
view.add_command(list_)
