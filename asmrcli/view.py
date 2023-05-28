import click
from asmrcli.core import rj_argument, id2rj


@click.group(help="some operation about view_path")
def view():
    pass


@click.command()
@rj_argument
def add(rj_id: int):
    """add an ASMR to view path (use symbolic link)"""
    from asmrcli.core import id2rj, create_fm
    rj = id2rj(rj_id)
    fm = create_fm()

    if fm.could_view():
        fm.view(rj, replace=True)


@click.command('list')
def list_():
    """list all files in view path"""
    from asmrcli.core import create_fm

    fm = create_fm()
    rjs = fm.list_('view')
    print(*rjs, sep='\n')


@click.command()
@rj_argument
def remove(rj_id: int):
    """remove a file link in view path"""
    from asmrcli.core import create_fm
    fm = create_fm()
    fm.remove_view(id2rj(rj_id))


view.add_command(add)
view.add_command(list_)
view.add_command(remove)
