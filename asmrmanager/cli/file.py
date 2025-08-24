import re
from pathlib import Path
from typing import List, Tuple, Literal
import typing

import click

from asmrmanager.config import config
from asmrmanager.cli.core import (
    create_database,
    create_general_api,
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
    source_name = id2source_name(source_id)

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

        url2download.append(
            (
                recover["url"],
                fm.download_path / source_name / rel_path,
            )
        )

    from asmrmanager.cli.core import create_downloader_and_database

    downloader, _ = create_downloader_and_database()
    tasks = []
    for url, path in url2download:
        path.parent.mkdir(parents=True, exist_ok=True)
        tasks.append(
            downloader.downloader.process_download(url, path.parent, path.name)
        )

    downloader.run(*tasks)


@click.command()
@multi_rj_argument("local")
@click.option(
    "--no-convert",
    "-nc",
    is_flag=True,
    default=False,
    show_default=True,
    help="do not convert files before storing",
)
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
def store(
    source_ids: List[LocalSourceID],
    no_convert: bool,
    replace: bool,
    all_: bool,
):
    """
    store the downloaded files to the storage
    """

    def before_store_hook(path: Path):
        from asmrmanager.common.fileconverter import (
            AudioConverter,
            convert_vtt2lrc,
        )

        def convert(
            file: Path, to: Literal["mp3", "flac", "m4a", "wav", "lrc"]
        ):
            if file.suffix.lower() == f".{to}":
                logger.debug(f"{file} already in {to} format, skipping")
                return
            if to == "lrc":
                assert file.suffix.lower() == ".vtt"
                logger.debug(f"converting {file} to lrc")
                convert_vtt2lrc(file)
            else:
                logger.debug(f"converting {file} to {to}")
                with AudioConverter(f"Audio conversion to {to}") as converter:
                    converter.convert(file, dst=to)

            if len(file.suffixes) == 1:
                assert file.with_suffix(f".{to}").exists()
            logger.info("Removing old file: %s", file)
            file.unlink()

        def convert_all(
            from_: str,
            to: Literal["mp3", "flac", "m4a", "wav", "lrc"],
            threads: int = 6,
        ):
            if to == "lrc":
                for file in path.rglob(
                    f"*.{from_}", case_sensitive=False
                ):  # case_sensitive was added in python 3.12
                    if not file.is_dir():
                        convert(file, to)
            else:
                src_paths = list(
                    filter(
                        lambda p: not p.is_dir()
                        and p.suffix.lower() != f".{to}",
                        path.rglob(f"*.{from_}", case_sensitive=False),
                    )
                )
                if len(src_paths) == 0:
                    logger.info(
                        f"No files to convert from {from_} to {to} in {path}"
                    )
                    return
                with AudioConverter(
                    f"Audio conversion to {to}", threads=threads
                ) as converter:
                    converter.convert(*src_paths, dst=to)

                for src_path in src_paths:
                    if src_path.suffix.lower() == f".{to}":
                        continue
                    if src_path.with_suffix(f".{to}").exists():
                        logger.info("Removing old file: %s", src_path)
                        src_path.unlink()

        code = config.before_store
        logger.debug("executing before_store_hook code: %s", code)
        if not code.strip():
            return

        exec(
            code,
            {"path": path, "convert": convert, "convert_all": convert_all},
        )

    hook = None if no_convert else before_store_hook
    db = create_database()
    try:
        if all_:
            from asmrmanager.common.select import confirm

            res = confirm(
                "Are you sure to store all files in the download_path?",
            )
            if res is None or res is False:
                return
            fm.store_all(replace=replace, hook=hook)
            id_to_store = fm.list_("download")

        else:
            for rj_id in source_ids:
                fm.store(rj_id, replace=replace, hook=hook)
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
    "--offline",
    is_flag=True,
    default=False,
    show_default=True,
    help="Skip hash verification(By default hash verification is enabled, "
    "which takes a long time for calculating and web request)",
)
@click.option(
    "--list",
    "list_",
    is_flag=True,
    default=False,
    show_default=True,
    help="only list source id (pipe it to `dl get --force` to redownload them)",
)
def check(list_: bool, offline: bool):
    """
    check for download path for files to be downloaded correctly without missing or fail.
    """
    # TODO: check hash with xxhash3
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
            continue

        if offline:
            continue

        remote_files_should_down_list = [
            Path(i["path"]) for i in recovers if i["should_download"]
        ]
        file_ids = [i.get("fileId") for i in recovers if i["should_download"]]
        if not all(isinstance(i, int) for i in file_ids):
            logger.warning(
                f"source_id {source_id} has missing fileId in recover, "
                "please update your recover file first"
            )
            continue
        file_ids = typing.cast(List[int], file_ids)
        # file_ids = [int(i.split("/")[1]) for i in file_ids]

        file_paths: List[Path] = []
        for file in remote_files_should_down_list:
            file_path = fm.get_path(source_id, str(file), prefer="download")
            assert file_path is not None, (
                f"Unexpected None value for file path = {file_path}"
                " and source_id = {source_id}"
            )
            if not (file_path.exists() and file_path.is_file()):
                if fm.check_exists(f"{id2source_name(source_id)}/{str(file)}"):
                    logger.warning(
                        f"file {file_path} seems to be deleted, but another "
                        "file with same name and different extension exists"
                    )
                else:
                    logger.error(
                        f"file {file_path} does not exist or is not a file"
                    )
                continue

            file_paths.append(file_path)

        api = create_general_api()
        res = api.run(
            *[
                api.verify(file_path, file_id)
                for file_path, file_id in zip(file_paths, file_ids)
            ]
        )
        if not all(res):
            logger.error(
                f"source_id {source_id} has files that failed to verify hash:"
            )
            for i, (file_path, file_id) in enumerate(
                zip(file_paths, file_ids)
            ):
                if not res[i]:
                    logger.error(f"fileId: {file_id}, {file_path}")
            if list_:
                print(source_id)
            continue
        else:
            logger.info(
                f"source_id {source_id} has all files verified successfully"
            )


file.add_command(del_)
file.add_command(recover)
file.add_command(store)
file.add_command(diff)
file.add_command(check)
