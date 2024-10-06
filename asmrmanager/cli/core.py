import functools
import uuid
from typing import TYPE_CHECKING, Any, List, Literal, Tuple

import asyncstdlib
import click

from asmrmanager.common.browse_params import BrowseParams
from asmrmanager.common.download_params import DownloadParams
from asmrmanager.common.parse_filter import name_should_download
from asmrmanager.common.rj_parse import (
    id2source_name,
    is_local_source_id,
    is_remote_source_id,
    source2id,
    source_name2id,
)
from asmrmanager.common.types import LocalSourceID, RemoteSourceID, SourceID
from asmrmanager.config import config
from asmrmanager.filemanager.manager import FileManager
from asmrmanager.logger import logger
from asmrmanager.spider.asmrapi import ASMRAPI

fm = FileManager.get_fm()

if config.api_channel:
    ASMRAPI.set_api_channel(config.api_channel)

if TYPE_CHECKING:
    from asmrmanager.database.manage import DataBaseManager
    from asmrmanager.spider import ASMRDownloadManager


def create_database(
    skip_check: bool = False,
):  # skip_check is only used for migration
    from asmrmanager.database.manage import DataBaseManager

    db = DataBaseManager(tag_filter=config.tag_filter or tuple())
    if not skip_check and not db.check_db_updated():
        logger.error(
            "Your database is out dated, Please update your database schema"
            " with asmr utils migrate!"
        )
        exit(-1)
    return db


def create_downloader_and_database(
    download_params: DownloadParams | None = None,
) -> Tuple["ASMRDownloadManager", "DataBaseManager"]:
    from asmrmanager.spider import ASMRDownloadManager

    db = create_database()

    if download_params is None:
        download_params = DownloadParams(False, False, True, True)

    def id_should_download(source_id: RemoteSourceID):
        # TODO update this function with LocalSourceID
        return not db.check_exists(source_id)
        # return False
        # local_source_id = convert2local_id(source_id)
        # if local_source_id is None:
        #     return False
        # return fm.get_location(local_source_id) is None

    return (
        ASMRDownloadManager(
            name=config.username,
            password=config.password,
            proxy=config.proxy,
            id_should_download=(
                (lambda _: True)
                if download_params.force
                else id_should_download
            ),  # 如果数据库中不存在或者文件不存在，都执行下载
            json_should_download=lambda info: db.add_info(
                info, check=download_params.check_tag
            ),
            name_should_download=(
                name_should_download
                if download_params.check_name
                else (lambda *_: True)
            ),
            replace=download_params.replace,
            download_method=config.download_method,
            aria2_config=config.aria2_config,
        ),
        db,
    )


def create_playlist():
    from asmrmanager.spider.interface import ASMRPlayListManager

    return ASMRPlayListManager(
        name=config.username, password=config.password, proxy=config.proxy
    )


def browse_param_options(f):
    """pass the `browse_params` parameter to the function"""

    @click.option(
        "-p",
        "--page",
        type=int,
        default=1,
        help="page of the search result, speicify to 0 if you want to download all pages",
        show_default=True,
    )
    @click.option(
        "--subtitle/--no-subtitle",
        is_flag=True,
        default=False,
        help="if the ASMR has subtitle(中文字幕)",
        show_default=True,
    )  # no -s/-ns option for ocnfliction with --sell -s
    @click.option(
        "-o",
        "--order",
        type=click.Choice(
            [
                "create_date",
                "rating",
                "release",
                "dl_count",
                "price",
                "rate_average_2dp",
                "review_count",
                "id",
                "nsfw",
                "random",
            ],
            case_sensitive=False,
        ),
        default="release",
        help="ordering of the search result",
        show_default=True,
    )
    @click.option(
        "--asc/--desc", default=False, help="ascending or descending"
    )
    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        keys = ["page", "subtitle", "order", "asc"]
        browse_params = BrowseParams(**{k: kwargs.pop(k) for k in keys})
        return f(*args, **kwargs, browse_params=browse_params)

    wrapper_common_options.__doc__ = (
        ""
        if wrapper_common_options.__doc__ is None
        else wrapper_common_options.__doc__
    )
    wrapper_common_options.__doc__ += """

    nsfw will only show the full age ASMRs

    for other --order values, you can refer to the website for
    explicit meaning
    """

    return wrapper_common_options


def download_param_options(f):
    """pass the `download_params` parameter to the function"""

    @click.option(
        "--force/--check-db",
        is_flag=True,
        default=False,
        help=(
            "force download even if the RJ id exists in database,"
            "or by default, RJ already in the database will be skipped"
        ),
    )
    @click.option(
        "--replace/--no-replace",
        is_flag=True,
        default=False,
        show_default=True,
        help="replace the file if it exists",
    )
    @click.option(
        "--check-name/--ignore-name",
        is_flag=True,
        default=True,
        show_default=True,
        help=(
            "check and filter out asmr by filenames, rules are in the config"
            " file"
        ),
    )
    @click.option(
        "--check-tag/--ignore-tag",
        is_flag=True,
        default=True,
        show_default=True,
        help="check and filter out asmr by tags, rules are in the config file",
    )
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        keys = ["force", "replace", "check_name", "check_tag"]
        download_params = DownloadParams(**{k: kwargs.pop(k) for k in keys})
        return f(*args, **kwargs, download_params=download_params)

    wrap.__doc__ = "" if wrap.__doc__ is None else wrap.__doc__
    wrap.__doc__ += """

    --force will check the download RJ files again though it is already
     in the database, it work just like update

    --replace option will first delte the original file,
    then add the new file to download queue(i.e. IDM or aria2)
    """
    return wrap


PREVIOUS_RJ_PATH = fm.DATA_PATH / ".prev_rj"


def get_prev_source():
    if not PREVIOUS_RJ_PATH.exists():
        return ""
    rj = PREVIOUS_RJ_PATH.read_text(encoding="utf8")
    logger.info(f"previous RJ id is {rj}")
    return rj


def save_source(rj: str):
    PREVIOUS_RJ_PATH.write_text(rj, encoding="utf8")


def convert2local_ids(
    source_ids: List[SourceID],
) -> List[LocalSourceID | None]:
    downloader, db = create_downloader_and_database()

    @asyncstdlib.lru_cache(None)
    async def convert2local_id(source_id: SourceID):
        if is_local_source_id(source_id):
            return LocalSourceID(source_id)
        source_id = RemoteSourceID(source_id)
        res = db.func.get_local_id(source_id)
        if res is not None:
            return LocalSourceID(SourceID(res))
        info = await downloader.downloader.get_voice_info(source_id)
        return LocalSourceID(source_name2id(info["source_id"]))

    return downloader.run(
        *[convert2local_id(remote_id) for remote_id in source_ids]
    )


def convert2local_id(x):
    return convert2local_ids([x])[0]


def convert2remote_ids(
    source_ids: List[SourceID],
) -> List[RemoteSourceID | None]:
    downloader, db = create_downloader_and_database()

    @asyncstdlib.lru_cache(None)
    async def convert2remote_id(source_id: SourceID):
        if is_remote_source_id(source_id):
            return RemoteSourceID(source_id)
        source_id = LocalSourceID(source_id)
        res = db.func.get_remote_id(source_id)
        if res is not None:
            return RemoteSourceID(SourceID(res))
        source_name = id2source_name(source_id)
        res = await downloader.downloader.get_search_result(source_name, {})
        works = res["works"]
        if len(works) == 0:
            logger.warning(f"no remote resources for {source_name}")
            return None
        if len(works) > 1:
            logger.warning(
                f"multiple remote resources for {source_name}, choose the"
                " first one by default"
            )
        return works[0]["id"]

    return downloader.run(
        *[convert2remote_id(local_id) for local_id in source_ids]
    )


def convert2remote_id(x):
    return convert2remote_ids([x])[0]


def rj_argument(convert: Literal[False, "local", "remote"] = False):
    """parse the source_id: int, if not given it will use the previous source_id"""

    def _(f):
        @click.argument("source_id", type=str, default="__default__")
        @functools.wraps(f)
        def __(*args, **kwargs):
            source: str = kwargs["source_id"]
            if kwargs["source_id"] == "__default__":
                source = get_prev_source()
            if source == "":
                logger.error(
                    "No previous source id available,"
                    " please first run a command with source id"
                )
                exit(-1)

            source_id = source2id(source)
            if source_id is None:
                logger.error(f"Invalid input source id: {source}")
                exit(-1)
            if convert == "local" and not is_local_source_id(source_id):
                source_id = convert2local_id(source_id)
            elif convert == "remote" and not is_remote_source_id(source_id):
                source_id = convert2remote_id(source_id)

            if source_id is None:
                logger.error(f"failed to convert to {convert} source id")
                exit(-1)

            save_source(source)
            kwargs["source_id"] = source_id

            f(*args, **kwargs)

        return __

    return _


def multi_rj_argument(convert: Literal[False, "local", "remote"] = False):
    """parse multiple rj input to rj_id"""

    def _(f):
        @click.argument("source_ids", nargs=-1)
        @functools.wraps(f)
        def __(*args, **kwargs):
            sources: Tuple[str] = kwargs["source_ids"]
            del kwargs["source_ids"]
            source_ids: List[Any] = []
            for source in sources:
                source_id = source2id(source)
                if source_id is None:
                    logger.error(f"Invalid input source id: {source}")
                    continue
                source_ids.append(source_id)
            if convert == "local":
                source_ids = convert2local_ids(source_ids)
            elif convert == "remote":
                source_ids = convert2remote_ids(source_ids)
            source_ids = [x for x in source_ids if x is not None]

            if len(source_ids) == 0:
                source = get_prev_source()
                if source == "":
                    logger.error(
                        "No previous source id available,"
                        " please first run a command with source id"
                    )
                    exit(-1)

                source_id = source2id(source)
                if source_id is None:
                    logger.error(f"Invalid input source id: {source}")
                    exit(-1)

                if convert == "local":
                    source_id = convert2local_id(source_id)
                elif convert == "remote":
                    source_id = convert2remote_id(source_id)

                if source_id is None:
                    logger.error(f"failed to convert to {convert} source id")
                    exit(-1)
                source_ids.append(source_id)
            elif len(source_ids) == 1:
                save_source(str(source_ids[0]))

            f(*args, source_ids=source_ids, **kwargs)

        return __

    return _


SEPARATOR = ":"


def interval_preprocess_cb(ctx: click.Context, opt: click.Parameter, val: str):
    """
    input must be numeric or None,
    and it returns a float/int/str/None value tuple
    """
    if val is None:
        return (None, None)
    vals = val.split(SEPARATOR)
    assert len(vals) == 2

    def _check(x: str):
        if x == "":
            return None

        if not x.isdigit():
            if x[-1] in "hm" and x[:-1].isdigit():
                return x
            logger.warning(f"{x} is not a valid number or time")
            return None

        xf: float = float(x)
        if xf.is_integer():
            return int(xf)
        return xf

    return tuple(map(_check, vals))


def time_interval_preprocess_cb(
    ctx: click.Context, opt: click.Parameter, val: str
):
    return tuple(
        map(
            lambda x: str(x) + "m"
            if (x is not None) and (not isinstance(x, str))
            else x,
            interval_preprocess_cb(ctx, opt, val),
        )
    )


def pl_preprocess_cb(
    ctx: click.Context, param: click.Option, val: str | Tuple
) -> List[uuid.UUID]:
    def is_valid_uuid(v: str):
        try:
            uuid.UUID(v)
            return True
        except ValueError:
            return False

    if isinstance(val, str):
        val = (val,)

    res = []

    # check for valid uuid
    possible_aliaes = []
    for v in val:
        if is_valid_uuid(v):
            res.append(v)
            continue
        else:
            possible_aliaes.append(v)

    # make transfromation from alias to uuid or name
    possible_names = []
    for alias in possible_aliaes:
        name_or_uuid = config.playlist_aliases.get(alias, alias)
        if is_valid_uuid(name_or_uuid):
            res.append(name_or_uuid)
        else:
            possible_names.append(name_or_uuid)

    # check and get cached playlist
    playlists_cache = fm.get_playlist_cache()
    if playlists_cache is None:
        logger.warning("no cached playlist, try getting from server")
        pl = create_playlist()
        # TODO use to CONSTANT to replace 100
        playlists_cache, total = pl.run(
            pl.playlist.get_playlists(page_size=100)
        )[0]
        if total > len(playlists_cache):
            logger.warning(
                f"total playlist number {total} is larger than"
                f" {len(playlists_cache)}"
            )
        fm.save_playlist_cache(playlists_cache)
    cached_names = [p.name for p in playlists_cache]

    # check for valid names using playlist cache
    for name in possible_names:
        if name in cached_names:
            res.append(playlists_cache[cached_names.index(name)].id)
        else:
            logger.warning(f"invalid playlist name {name}")

    if not res:
        logger.warning(
            "If you just have created a playlist, you may need to use pl list"
            " to cache the playlists to local"
        )
        ctx.fail("no valid uuid, alias or names found")

    if param.nargs == 1:
        return res[0]
    return res
