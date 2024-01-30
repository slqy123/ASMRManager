import click

from asmrmanager.cli.core import (
    create_database,
    create_downloader_and_database,
    rj_argument,
)
from asmrmanager.common.rj_parse import RJID
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
    tags = "\n".join([f"  - {t}" for t in asmr.tags])
    cvs = "\n".join([f"  - {c}" for c in asmr.vas])
    s = template.format(tags=tags, cvs=cvs, **res)
    console = Console()
    console.print(Markdown(s))


def info_from_web(rj_id: int):
    downloader, db = create_downloader_and_database()
    (rj_info,) = downloader.run(downloader.downloader.get_voice_info(rj_id))

    res = db.parse_info(rj_info)
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
@rj_argument
def info(rj_id: RJID, rand: bool):
    """show info of the ASMR by id"""
    db = create_database()

    v_info = db.func.get_info(rj_id, rand=rand)
    if v_info is None:
        logger.info(f"RJ{rj_id} not exists, try getting from web")
        info_from_web(rj_id)
        return

    print_asmr_info(v_info)
