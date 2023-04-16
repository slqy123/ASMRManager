import click
from typing import Iterable, Optional
from asmrcli.core import create_spider_and_database, rjs2ids, browse_param_options
from common.browse_params import BrowseParams
from logger import logger

@click.group()
def dl():
    pass


@click.command()
@click.argument('ids', nargs=-1)
def get(ids: Iterable[str]):
    spider, db = create_spider_and_database()
    spider.run(spider.get(rjs2ids(ids)))
    db.commit()


@click.command()
@click.argument('ids', nargs=-1)
def update(ids: Iterable[str]):
    # ids = [(int(rj_id[2:]) if rj_id.startswith('RJ') else int(rj_id)) for rj_id in ids]
    spider, db = create_spider_and_database(dl_func='force')
    spider.run(spider.get(rjs2ids(ids)))
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
@click.option('tid', '-t', '--tag-id', type=int, default=None)
@browse_param_options
def tag(name: str, tid: int, **kwargs):
    if (bool(name) + bool(tid)) != 1:
        logger.error('You must give and should only give one param!')
        return
    params = BrowseParams(**kwargs)
    spider, db = create_spider_and_database()
    if tid:
        tag_res: Optional[str] = db.func.get_tag_name(tid)
        if tag_res is None:
            logger.error('tag id is not in the database!')
            return
        name = tag_res

    spider.run(spider.tag(name, params))
    db.commit()


dl.add_command(get)
dl.add_command(update)
dl.add_command(search)
dl.add_command(tag)
