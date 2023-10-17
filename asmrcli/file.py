import click
from asmrcli.core import rj_argument
from common.rj_parse import RJID
from logger import logger
from typing import Dict, List, Tuple, Any
from pathlib import Path
import re


@click.group()
def file():
    """file management"""
    pass


@click.command("del")
@rj_argument
def del_(rj_id: RJID):
    """not implemented"""
    raise NotImplementedError
    from filemanager.utils import folder_chooser_multiple
    from asmrcli.core import create_fm

    fm = create_fm()

    rj_path = fm.get_path(rj_id)

    if rj_path is None:
        logger.error(f"item {rj_id} does not exists")
        return

    folders = folder_chooser_multiple(
        rj_path,
        lambda p: any(
            [i.suffix != ".info" for i in p.iterdir() if not i.is_dir()]
        ),
    )

    for folder in folders:
        pass


@click.command()
@rj_argument
@click.option(
    "--regex", "-r", type=str, default=".*", help="use regex to match"
)
@click.option(
    "--ignore-filter",
    "-i",
    "ignore_filter",
    is_flag=True,
    default=False,
    show_default=True,
    help="recover files that have been filtered out",
)
def recover(rj_id: RJID, regex: str, ignore_filter: bool):
    """recover a file from recover file"""
    from asmrcli.core import create_fm

    fm = create_fm()
    rj_path = fm.get_path(rj_id)
    if rj_path is None:
        logger.error(f"item {rj_id} does not exist")
        return

    recover_path = rj_path / ".recover"
    if not recover_path.exists():
        logger.error(
            f"item {rj_id} does not have recover file, please update this"
            " rj id first"
        )
        return

    import json

    recovers: List[Dict[str, Any]] = json.loads(
        recover_path.read_text(encoding="utf8")
    )

    url2download: List[Tuple[str, Path]] = []

    for recover in recovers:
        rel_path = recover["path"]

        recover_file = rj_path / rel_path
        if recover_file.exists():
            continue

        if not re.search(regex, rel_path):
            continue

        if not recover["should_download"]:
            if not ignore_filter:
                logger.info(
                    f"file {rel_path} is filtered out and should not be"
                    " recovered"
                )
                continue
            else:
                logger.warning(
                    f"recover file {rel_path} since filters are ignored"
                )

        url2download.append((recover["url"], recover_file))

    from asmrcli.core import create_spider_and_database

    spider, _ = create_spider_and_database()
    for url, path in url2download:
        spider.spider.process_download(url, path.parent, path.name)


file.add_command(del_)
file.add_command(recover)
