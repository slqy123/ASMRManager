import re
from pathlib import Path
from typing import List, Tuple, Literal

import click

from asmrmanager.config import config
from asmrmanager.cli.core import (
    create_database,
    fm,
    multi_rj_argument,
    rj_argument,
)
from asmrmanager.common.rj_parse import id2source_name
from asmrmanager.common.types import LocalSourceID
from asmrmanager.filemanager.exceptions import DstItemAlreadyExistsException
from asmrmanager.logger import logger


@click.group()
def file():
    """file management"""


@click.command("del")
@rj_argument("local")
def del_(source_id: LocalSourceID):
    """not implemented"""
    raise NotImplementedError
    from asmrmanager.cli.core import create_fm
    from asmrmanager.filemanager.utils import folder_chooser_multiple

    fm = create_fm()

    rj_path = fm.get_path(source_id)

    if rj_path is None:
        logger.error(f"item {source_id} does not exists")
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
@rj_argument("local")
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
def recover(source_id: LocalSourceID, regex: str, ignore_filter: bool):
    """recover a file from recover file"""

    url2download: List[Tuple[str, Path]] = []

    res = fm.load_recover(source_id)
    if res is None:
        return
    recovers = res

    files = fm.get_all_files(source_id)

    for recover in recovers:
        rel_path = recover["path"]

        # recover_file = rj_path / rel_path
        # if recover_file.exists():
        #     continue
        if rel_path in files:
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

        url2download.append((recover["url"], fm.download_path / rel_path))

    from asmrmanager.cli.core import create_downloader_and_database

    downloader, _ = create_downloader_and_database()
    tasks = []
    for url, path in url2download:
        tasks.append(
            downloader.downloader.process_download(url, path.parent, path.name)
        )

    downloader.run(*tasks)


@click.command()
@multi_rj_argument("local")
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
def store(source_ids: List[LocalSourceID], replace: bool, all_: bool):
    """
    store the downloaded files to the storage
    """

    def before_store_hook(path: Path):
        from asmrmanager.common.fileconverter import (
            convert_audio_format,
            convert_vtt2lrc,
        )

        def convert(
            file: Path, to: Literal["mp3", "flac", "m4a", "wav", "lrc"]
        ):
            if to == "lrc":
                assert file.suffix.lower() == ".vtt"
                logger.debug(f"converting {file} to lrc")
                convert_vtt2lrc(file)
            else:
                logger.debug(f"converting {file} to {to}")
                convert_audio_format(file, to)

            if len(file.suffixes) == 1:
                assert file.with_suffix(f".{to}").exists()
            file.unlink()

        def convert_all(
            from_: str, to: Literal["mp3", "flac", "m4a", "wav", "lrc"]
        ):
            for file in path.rglob(f"*.{from_}", case_sensitive=False):
                convert(file, to)

        code = config.before_store
        logger.debug("executing before_store_hook code: %s", code)
        if not code.strip():
            return

        exec(
            code,
            {"path": path, "convert": convert, "convert_all": convert_all},
        )

    db = create_database()
    try:
        if all_:
            from asmrmanager.common.select import confirm

            res = confirm(
                "Are you sure to store all files in the download_path?",
            )
            if res is None or res is False:
                return
            fm.store_all(replace=replace, hook=before_store_hook)
            id_to_store = fm.list_("download")

        else:
            for rj_id in source_ids:
                fm.store(rj_id, replace=replace, hook=before_store_hook)
            id_to_store = source_ids

        for id_ in id_to_store:
            res = db.check_exists(id_)
            if not res:
                logger.error(
                    "no such id: %s, which is an unexpected situation", id_
                )
                continue
            res.stored = True
        logger.info("succesfully stored all files")
    except DstItemAlreadyExistsException as e:
        logger.error("storing terminated for %s", e)
    finally:
        db.commit()


@click.command()
@rj_argument("local")
def diff(source_id: LocalSourceID):
    """
    Diff local files and the remote files,
    display files filtered, missing and added
    """
    if res := fm.load_recover(source_id):
        recovers = res
    else:
        return

    local_files = fm.get_all_files(source_id)

    remote_files_should_down = set(
        [Path(i["path"]) for i in recovers if i["should_download"]]
    )
    remote_files_filterd = set(
        [Path(i["path"]) for i in recovers if not i["should_download"]]
    )
    filtered_but_downloaded = remote_files_filterd & local_files
    should_download_but_missing = remote_files_should_down - local_files
    added_new_files = (
        local_files - remote_files_should_down - remote_files_filterd
    )

    all_files = local_files | remote_files_should_down | remote_files_filterd

    color_map = {}
    for file in all_files:
        if file in filtered_but_downloaded:
            color_map[file] = "yellow"
        elif file in should_download_but_missing:
            color_map[file] = "red"
        elif file in added_new_files:
            color_map[file] = "green"
        elif file in (remote_files_filterd - filtered_but_downloaded):
            color_map[file] = "dim"
        else:
            color_map[file] = "tree"

    from rich import print
    from rich.tree import Tree

    tree = Tree(id2source_name(source_id))
    p2tree = {Path("."): tree}
    for file in sorted(all_files, key=lambda x: x.parts):
        # if p2tree.get(file.parent) is None:
        #     p2tree[file.parent] = Tree(file.parent.name)
        # p2tree[file.parent].add(file.name, style=color_map[file])
        for path in reversed(file.parents):  # from . → ./a → ./a/b
            if p2tree.get(path) is None:
                p2tree[path] = Tree(path.name)
                p2tree[path.parent].add(p2tree[path])

        p2tree[file.parent].add(file.name, style=color_map[file])

    print(tree)


@click.command()
@click.option(
    "--list",
    "list_",
    is_flag=True,
    default=False,
    show_default=True,
    help="only list source id (pipe it to `dl get --force` to redownload them)",
)
def check(list_: bool):
    """
    check for download path for files to be downloaded without missing or failed
    """
    source_ids = fm.list_("download")
    for source_id in source_ids:
        if res := fm.load_recover(source_id):
            recovers = res
        else:
            logger.error(f"failed to load recover for id {source_id}")
            if list_:
                print(source_id)
            continue

        # local_files = fm.get_all_files(source_id)
        remote_files_should_down = set(
            [Path(i["path"]) for i in recovers if i["should_download"]]
        )
        # should_download_but_missing = remote_files_should_down - local_files
        should_download_but_missing = set(
            filter(
                lambda p: not any(
                    fm.check_exists(f"{id2source_name(source_id)}/{str(p)}")
                ),
                remote_files_should_down,
            )
        )
        if len(should_download_but_missing):
            logger.error(
                f"source_id {source_id} has missing files:\n"
                + "\n".join(str(p) for p in should_download_but_missing)
            )
            if list_:
                print(source_id)


file.add_command(del_)
file.add_command(recover)
file.add_command(store)
file.add_command(diff)
file.add_command(check)
