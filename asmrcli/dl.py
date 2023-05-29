import click
from typing import Iterable, Optional, Tuple
from asmrcli.core import create_spider_and_database, rjs2ids, browse_param_options, rj_argument
from common.browse_params import BrowseParams
from logger import logger


@click.group(help="download ASMR")
def dl():
    pass


@click.command()
@click.argument('ids', nargs=-1)
def get(ids: Iterable[str]):
    """get ASMR by RJ ids"""
    spider, db = create_spider_and_database()
    spider.run(spider.get(rjs2ids(ids)))
    db.commit()


@click.command()
@click.argument('ids', nargs=-1)
def update(ids: Iterable[str]):
    """Not implemented"""
    # ids = [(int(rj_id[2:]) if rj_id.startswith('RJ') else int(rj_id)) for rj_id in ids]
    spider, db = create_spider_and_database(dl_func='force')
    spider.run(spider.get(rjs2ids(ids)))
    db.commit()


@click.command()
@click.argument('text', type=str, default='')
@click.option('--tags', '-t', type=str, multiple=True, help='tags to include[multiple]')
@click.option('--no-tags', '-nt', type=str, multiple=True, help='tags to exclude[multiple]')
@click.option('--vas', '-v', type=str, multiple=True, help='voice actor(cv) to include[multiple]')
@click.option('--no-vas', '-nv', type=str, multiple=True, help='voice actor(cv) to exclude[multiple]')
@click.option('--circle', '-c', type=str, default=None, help='circle(社团) to include')
@click.option('--no-circle', '-nc', type=str, multiple=True, help='circle(社团) to exclude[multiple]')
@browse_param_options
def search(text: str, tags: Tuple[str], vas: Tuple[str], circle: str | None,
           no_tags: Tuple[str], no_vas: Tuple[str], no_circle: Tuple[str],
           **kwargs):
    """
    search and download ASMR by filters

    attention the [multiple] options, this means you can add multiple same option such as:

        --tags tag1 --tags tag2 --no-tags tag3
    """
    params = BrowseParams(**kwargs)
    spider, db = create_spider_and_database()
    spider.run(spider.search(text, tags=tags, vas=vas, circle=circle,
                             no_tags=no_tags, no_vas=no_vas, no_circle=no_circle,
                             params=params))
    db.commit()


@click.command()
@click.option('-n', '--name', type=str, default=None, show_default=True, help='tag name')
@click.option('tid', '-t', '--tag-id', type=int, default=None, show_default=True, help='tag id')
@browse_param_options
def tag(name: str, tid: int, **kwargs):
    """search ASMR by tags. either tagname or tagid could use.
    if search by tagid, the id must be in the local database"""
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
