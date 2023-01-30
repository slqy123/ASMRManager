import click
from typing import Iterable
from asmrcli.core import create_spider_and_database, rjs2ids


@click.group()
def dl():
    pass


@click.command()
@click.argument('ids', nargs=-1)
def get(ids: Iterable[str]):
    ids = rjs2ids(ids)
    spider, db = create_spider_and_database()
    spider.run(spider.get(ids))
    db.commit()


@click.command()
@click.argument('ids', nargs=-1)
def update(ids: Iterable[str]):
    # ids = [(int(rj_id[2:]) if rj_id.startswith('RJ') else int(rj_id)) for rj_id in ids]
    ids = rjs2ids(ids)
    spider, db = create_spider_and_database()
    spider.run(spider.update_info(ids))
    db.commit()


@click.command()
@click.argument('text', type=str, default='')
@click.option('-p', '--page', type=int, default=1)
@click.option('-s', '--subtitle', is_flag=True, default=False)
def search(text: str, page: int, subtitle: bool):
    spider, db = create_spider_and_database()
    spider.run(spider.search(text, page, subtitle=subtitle))
    db.commit()


dl.add_command(get)
dl.add_command(update)
dl.add_command(search)
