from pprint import pprint

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
    res: dict = asmr.__dict__.copy()
    res.pop("_sa_instance_state")
    pprint(res)
    print(" tags:", asmr.tags)
    print(" CVs:", asmr.vas)


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
