import click


@click.group()
def view():
    pass


@click.command()
@click.argument('rj_id', type=str)
def add(rj_id: str):
    from asmrcli.core import rj2id, id2rj, create_fm
    rj_id_int = rj2id(rj_id)
    assert isinstance(rj_id_int, int)
    rj = id2rj(rj_id_int)
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
