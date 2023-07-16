import click
from typing import Iterable, Optional, Tuple
from asmrcli.core import create_spider_and_database, rjs2ids, browse_param_options, rj_argument, interval_preprocess_cb
from common.browse_params import BrowseParams
from logger import logger


@click.group(help="download ASMR")
def dl():
    pass


@click.command()
@click.option('--force', '-f', is_flag=True, type=bool, default=False, show_default=True,
              help='force to download though the RJ id is already in the database')
@click.argument('ids', nargs=-1)
def get(ids: Iterable[str], force: bool):
    """get ASMR by RJ ids"""
    if not ids:
        logger.error('You must give at least one RJ id!')
        return
    spider, db = create_spider_and_database(
        'db_not_exists' if not force else 'force')
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
@click.option('--rate', '-r',  help="rating interval", callback=interval_preprocess_cb)
@click.option('--sell', '-s',  help="selling interval", callback=interval_preprocess_cb)
@click.option('--price', '-pr', help="pirce interval", callback=interval_preprocess_cb)
@browse_param_options
def search(text: str, tags: Tuple[str], vas: Tuple[str], circle: str | None,
           no_tags: Tuple[str], no_vas: Tuple[str], no_circle: Tuple[str],
           rate: Tuple[float | None, float | None], sell: Tuple[int | None, int | None], price: Tuple[int | None, int | None],
           **kwargs):
    """
    search and download ASMR by filters

    the [multiple] options means you can add multiple same option such as:

        --tags tag1 --tags tag2 --no-tags tag3

    for options like --rate, --sell, --price, you should give a interval like:

        --rate 3.9:4.7 --sell 1000: --price :200

    the interval a:b means a <= x < b, if a or b is not given i.e. a: or :b, it means no lower or upper limit
    """
    params = BrowseParams(**kwargs)
    spider, db = create_spider_and_database()
    spider.run(spider.search(text, tags=tags, vas=vas, circle=circle,
                             no_tags=no_tags, no_vas=no_vas, no_circle=no_circle,
                             rate=rate, sell=sell, price=price,
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
