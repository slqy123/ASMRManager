import click
from asmrmanager.cli.core import rj_argument, create_database, multi_rj_argument
from asmrmanager.cli.core import fm
from asmrmanager.filemanager.exceptions import DstItemAlreadyExistsException
from asmrmanager.common.rj_parse import RJID
from asmrmanager.logger import logger
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
    from asmrmanager.filemanager.utils import folder_chooser_multiple
    from asmrmanager.cli.core import create_fm

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

    from asmrmanager.cli.core import create_spider_and_database

    spider, _ = create_spider_and_database()
    for url, path in url2download:
        spider.spider.process_download(url, path.parent, path.name)


@click.command()
@multi_rj_argument
@click.option(
    "--replace/--no-replace",
    "-r/-nr",
    is_flag=True,
    default=True,
    show_default=True,
    help="replace the files if exists",
)
@click.option(
    "--all",
    "-a",
    "all_",
    is_flag=True,
    default=False,
    show_default=True,
    help="store all files",
)
def store(rj_ids: List[RJID], replace: bool, all_: bool):
    """
    store the downloaded files to the storage
    """

    db = create_database()
    try:
        if all_:
            import cutie

            res = cutie.prompt_yes_or_no(
                "Are you sure to store all files in the download_path?",
            )
            if res is None or res is False:
                return
            fm.store_all(replace=replace)
            id_to_store = fm.list_("download")

        else:
            for rj_id in rj_ids:
                fm.store(rj_id, replace=replace)
            id_to_store = rj_ids

        for id_ in id_to_store:
            res = db.check_exists(id_)
            if not res:
                logger.error(
                    "no such id: %s, which is an unexpected situation", id_
                )
                continue
            res.stored = True
        db.commit()
        logger.info("succesfully stored all files")
    except DstItemAlreadyExistsException as e:
        logger.error("storing terminated for %s", e)


file.add_command(del_)
file.add_command(recover)
file.add_command(store)