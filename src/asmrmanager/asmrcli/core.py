import os.path
from pathlib import Path
from common.browse_params import BrowseParams
from common.download_params import DownloadParams

from config import config
from logger import logger
from common.parse_filter import name_should_download
from common.rj_parse import id2rj, rj2id

from typing import Tuple, TYPE_CHECKING

import click
import functools

if TYPE_CHECKING:
    from spider import ASMRSpiderManager
    from database.manage import DataBaseManager


def create_database():
    from database.manage import DataBaseManager

    return DataBaseManager(tag_filter=config.tag_filter or tuple())


def create_spider_and_database(
    download_params: DownloadParams | None = None,
) -> Tuple["ASMRSpiderManager", "DataBaseManager"]:
    from spider import ASMRSpiderManager
    from filemanager.manager import fm

    db = create_database()

    if download_params is None:
        download_params = DownloadParams(False, False, False)

    return (
        ASMRSpiderManager(
            name=config.username,
            password=config.password,
            proxy=config.proxy,
            id_should_download=(
                (lambda _: True)
                if download_params.force
                else (
                    lambda rj_id: (not db.check_exists(rj_id))
                    or (fm.get_location(rj_id) is None)
                )
            ),  # 如果数据库中不存在或者文件不存在，都执行下载
            json_should_download=db.add_info,
            name_should_download=(
                name_should_download
                if download_params.filter
                else (lambda *_: True)
            ),
            replace=download_params.replace,
            download_method=config.download_method,
            aria2_config=config.aria2_config,
        ),
        db,
    )


# deprecated, use `from filemanager import fm` instead
# def create_fm():
#     from filemanager.manager import fm

#     return fm


def browse_param_options(f):
    """pass the `browse_params` parameter to the function"""

    @click.option(
        "-p",
        "--page",
        type=int,
        default=1,
        help="page of the search result",
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
        "--filter/--no-filter",
        is_flag=True,
        default=True,
        show_default=True,
        help="filter out the files to download, rules are in the config file",
    )
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        keys = ["force", "replace", "filter"]
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


def get_prev_rj():
    path = Path(__file__).parent.parent / ".prev_rj"
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf8") as f:
        rj = f.read()
    logger.info(f"previous RJ id is {rj}")
    return rj


def save_rj(rj: str):
    path = Path(__file__).parent.parent / ".prev_rj"
    with open(path, "w", encoding="utf8") as f:
        f.write(rj)


def rj_argument(f):
    """parse the rj_id: int, if not given it will use the previous rj_id"""

    @click.argument("rj_id", type=str, default="__default__")
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        rj: str = kwargs["rj_id"]
        if kwargs["rj_id"] == "__default__":
            rj = get_prev_rj()
        if rj == "":
            logger.error(
                "No previous RJ id available,"
                " please first run a command with Rj id"
            )
            exit(-1)

        rj_id = rj2id(rj)
        if rj_id is None:
            logger.error(f"Invalid input RJ ID{rj}")
            exit(-1)
        save_rj(rj)
        kwargs["rj_id"] = rj_id

        f(*args, **kwargs)

    return wrapper


def multi_rj_argument(f):
    """parse multiple rj input to rj_id"""

    @click.argument("rjs", nargs=-1)
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        rjs: Tuple[str] = kwargs["rjs"]
        del kwargs["rjs"]
        kwargs["rj_ids"] = []
        for rj in rjs:
            rj_id = rj2id(rj)
            if rj_id is None:
                logger.error(f"Invalid input RJ ID{rj}")
                continue
            kwargs["rj_ids"].append(rj_id)

        if len(kwargs["rj_ids"]) == 0:
            rj = get_prev_rj()
            if rj == "":
                logger.error(
                    "No previous RJ id available,"
                    " please first run a command with Rj id"
                )
                exit(-1)

            rj_id = rj2id(rj)
            if rj_id is None:
                logger.error(f"Invalid input RJ ID{rj}")
                exit(-1)
            kwargs["rj_ids"].append(rj_id)
        elif len(kwargs["rj_ids"]) == 1:
            save_rj(id2rj(kwargs["rj_ids"][0]))

        f(*args, **kwargs)

    return wrapper


SEPARATOR = ":"


def interval_preprocess_cb(ctx: click.Context, opt: click.Option, val: str):
    """
    input must be numeric or None,
    and it returns a float/int/None value tuple
    """
    if val is None:
        return (None, None)
    vals = val.split(SEPARATOR)
    assert len(vals) == 2

    def _check(x: str):
        if x == "":
            return None
        try:
            xf: float = float(x)
        except ValueError:
            ctx.fail(f"{x} is not a valid number")

        assert isinstance(xf, float)
        if xf.is_integer():
            return int(xf)
        return xf

    return tuple(map(_check, vals))
