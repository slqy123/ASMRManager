import click


@click.command()
@click.argument('rj_id', type=str)
@click.option('-s', '--star', type=int)
@click.option('-c', '--comment', type=str)
def review(rj_id: str, star: int = None, comment: str = None):
    rj_id = int(rj_id[2:]) if rj_id.startswith('RJ') else int(rj_id)

    from asmrcli.core import create_database
    db = create_database()
    db.update_review(rj_id, star, comment)
    db.commit()
