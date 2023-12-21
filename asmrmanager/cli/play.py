import os
from collections import Counter
from pathlib import Path

import click
import cutie

from asmrmanager.cli.core import create_database, fm, rj_argument
from asmrmanager.common.rj_parse import RJID, id2rj
from asmrmanager.config import config
from asmrmanager.logger import logger


@click.command()
@click.pass_context
@rj_argument
def play(ctx: click.Context, rj_id: RJID):
    """play an asmr in the terminal"""
    from asmrmanager.lrcplayer import lrc_play

    db = create_database()
    asmr = db.check_exists(rj_id)
    if asmr is None:
        logger.error(f"RJ id {rj_id} not found!")
        return
    asmr_rj = id2rj(asmr.id)

    loc = fm.get_location(asmr.id)
    if loc is None:
        logger.error(f"ASMR {asmr_rj} file not found!")
        return
    rj_path = (
        Path(fm.download_path) / asmr_rj
        if loc == "download"
        else Path(fm.storage_path) / asmr_rj
    )

    choices = []
    suf = [".mp3", ".wav", ".flac"]
    for path, _, files in os.walk(rj_path):
        res = Counter([Path(i).suffix for i in files])
        if not set(res.keys()).intersection(set(suf)):
            continue
        info = " ".join(
            [f"{key}: {val}" for key, val in res.items() if key in suf]
        )
        choices.append((path, info))

    idx: int = cutie.select([f"{x[0]} | [{x[1]}]" for x in choices])
    # it's just ok to use cutie, no need for beaupy
    # res = select(
    #     choices, preprocessor=lambda x: f'{x[0]} | [{x[1]}]',
    # return_index = True
    # )
    path = Path(choices[idx][0])

    ctx.invoke(lrc_play, path=path)
