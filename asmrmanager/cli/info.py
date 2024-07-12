import click

from asmrmanager.cli.core import (
    convert2remote_id,
    create_database,
    create_downloader_and_database,
    rj_argument,
)
from asmrmanager.common.types import LocalSourceID, RemoteSourceID
from asmrmanager.database.orm_type import ASMRInstance
from asmrmanager.logger import logger


def print_asmr_info(asmr: ASMRInstance):
    from rich.console import Console
    from rich.markdown import Markdown

    template = """
**{title}**
- id: {id}
- circle: {circle_name}
- nsfw: {nsfw}
- subtitle: {has_subtitle}
- price: {price}
- release date: {release_date}
- downloads: {dl_count}
- tags
{tags}
- CV
{cvs}

**comment**
- star: {star}
- review count: {count}
- held: {held}
- stored: {stored}

{comment}
    """
    res: dict = asmr.__dict__.copy()
    # logger.debug(res)
    tags = "\n".join([f"  - {t}" for t in asmr.tags])
    cvs = "\n".join([f"  - {c}" for c in asmr.vas])
    if res.get("tags"):
        del res["tags"]
    s = template.format(tags=tags, cvs=cvs, **res)
    console = Console()
    console.print(Markdown(s))


def info_from_web(source_id: RemoteSourceID):
    downloader, db = create_downloader_and_database()
    (rj_info,) = downloader.run(
        downloader.downloader.get_voice_info(source_id)
    )
    # logger.debug(rj_info)

    res = db.parse_info(rj_info)
    res.star = 0
    res.count = 0
    res.held = False
    res.stored = False
    res.comment = ""
    print_asmr_info(res)


@click.command()
@click.option(
    "--rand",
    "-r",
    is_flag=True,
    default=False,
    show_default=True,
    help="get a random info in the database",
)
@rj_argument("local")
def info(source_id: LocalSourceID, rand: bool):
    """show info of the ASMR by id"""
    db = create_database()

    v_info = db.func.get_info(source_id, rand=rand)
    if v_info is None:
        logger.info(f"{source_id} not exists, try getting from web")
        remote_source_id = convert2remote_id(source_id)
        if remote_source_id is None:
            logger.error(f"cannot convert {source_id} to remote id")
            return
        # logger.debug(f"converted {source_id} to {remote_source_id}")
        info_from_web(remote_source_id)
        return

    print_asmr_info(v_info)
