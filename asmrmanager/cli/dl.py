from typing import Iterable, Tuple

import click

from asmrmanager.cli.core import (
    browse_param_options,
    create_database,
    create_downloader_and_database,
    download_param_options,
    fm,
    interval_preprocess_cb,
    multi_rj_argument,
)
from asmrmanager.common.browse_params import BrowseParams
from asmrmanager.common.download_params import DownloadParams
from asmrmanager.common.rj_parse import RJID, id2rj
from asmrmanager.logger import logger


@click.group(help="download ASMR")
def dl():
    pass


@click.command()
@multi_rj_argument
@download_param_options
def get(rj_ids: Iterable[RJID], download_params: DownloadParams):
    """get ASMR by RJ ids"""
    if not rj_ids:
        logger.error("You must give at least one RJ id!")
        return
    spider, db = create_downloader_and_database(download_params)
    spider.run(spider.get(rj_ids))
    db.commit()


@click.command()
@multi_rj_argument
def update(rj_ids: Iterable[RJID]):
    """update metadata, including recover file and description file"""
    if not rj_ids:
        logger.error("You must give at least one RJ id!")
        return
    spider, db = create_downloader_and_database(
        DownloadParams(False, False, False, True)
    )
    spider.run(spider.update(rj_ids))
    db.commit()


@click.command()
@multi_rj_argument
def check(rj_ids: Iterable[RJID]):
    """check for existence of the file and its store field"""
    db = create_database()
    dl_queue = []
    for rj_id in rj_ids:
        rj = id2rj(rj_id)

        asmr = db.check_exists(rj_id)
        if asmr is None:
            logger.warning(
                f"Not found In Database: {rj}, please manually download it"
            )
            continue

        src = fm.get_location(rj_id)
        if src is None:
            logger.warning(f"Not found: {rj}, add to download")
            dl_queue.append(rj)
            continue

        if src == "download" and asmr.stored:
            logger.info(f"Already stored: {rj}, move to storage path")
            fm.store(rj_id)
            continue

        if src == "storage" and not asmr.stored:
            logger.info(f"Already in storage: {rj}, update database")
            asmr.stored = True
            continue

        logger.info(f"No need to update {rj}")
    db.commit()
    print("Update succesfully.")
    if dl_queue:
        print("Please check the item to download and get theme manually:")
        print(" ".join(dl_queue))


@click.command()
@click.argument("text", type=str, default="")
@click.option(
    "--tags", "-t", type=str, multiple=True, help="tags to include[multiple]"
)
@click.option(
    "--no-tags",
    "-nt",
    type=str,
    multiple=True,
    help="tags to exclude[multiple]",
)
@click.option(
    "--vas",
    "-v",
    type=str,
    multiple=True,
    help="voice actor(cv) to include[multiple]",
)
@click.option(
    "--no-vas",
    "-nv",
    type=str,
    multiple=True,
    help="voice actor(cv) to exclude[multiple]",
)
@click.option(
    "--circle", "-c", type=str, default=None, help="circle(社团) to include"
)
@click.option(
    "--no-circle",
    "-nc",
    type=str,
    multiple=True,
    help="circle(社团) to exclude[multiple]",
)
@click.option(
    "--rate", "-r", help="rating interval", callback=interval_preprocess_cb
)
@click.option(
    "--sell", "-s", help="selling interval", callback=interval_preprocess_cb
)
@click.option(
    "--price", "-pr", help="pirce interval", callback=interval_preprocess_cb
)
@click.option(
    "all_",
    "--all/--select",
    type=bool,
    is_flag=True,
    default=False,
    show_default=True,
    help="download all RJs",
)
@browse_param_options
@download_param_options
def search(
    text: str,
    tags: Tuple[str],
    vas: Tuple[str],
    circle: str | None,
    no_tags: Tuple[str],
    no_vas: Tuple[str],
    no_circle: Tuple[str],
    rate: Tuple[float | None, float | None],
    sell: Tuple[int | None, int | None],
    price: Tuple[int | None, int | None],
    browse_params: BrowseParams,
    download_params: DownloadParams,
    all_: bool,
):
    """
    search and download ASMR

    the [multiple] options means you can add multiple same option such as:

        --tags tag1 --tags tag2 --no-tags tag3

    for options like --rate, --sell, --price, you should give a interval like:

        --rate 3.9:4.7 --sell 1000: --price :200

    the interval a:b means a <= x < b, if a or b is not given
    i.e. a: or :b, it means no lower or upper limit
    """
    spider, db = create_downloader_and_database(
        download_params=download_params
    )
    spider.run(
        spider.search(
            text,
            tags=tags,
            vas=vas,
            circle=circle,
            no_tags=no_tags,
            no_vas=no_vas,
            no_circle=no_circle,
            rate=rate,
            sell=sell,
            price=price,
            params=browse_params,
            all_=all_,
        )
    )
    db.commit()


dl.add_command(get)
dl.add_command(check)
dl.add_command(search)
dl.add_command(update)
