import click
from typing import Iterable
from asmrcli.core import create_spider_and_database, rjs2ids, browse_param_options
from common.browse_params import BrowseParams

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
@browse_param_options
def search(text: str, **kwargs):
    params = BrowseParams(**kwargs)
    spider, db = create_spider_and_database()
    spider.run(spider.search(text, params))
    db.commit()


@click.command()
@click.option('-n', '--name', type=str, default=None)
@click.option('-t', '--tid', type=int, default=None)
@browse_param_options
def tag(name: str, tid: int, **kwargs):
    if (bool(name) + bool(tid)) != 1:
        print('error! You must give and should only give one param')
        return
    params = BrowseParams(**kwargs)
    spider, db = create_spider_and_database()
    if name:
        tid = db.func.get_tag_id(name)

    spider.run(spider.tag(tid, params))


dl.add_command(get)
dl.add_command(update)
dl.add_command(search)
