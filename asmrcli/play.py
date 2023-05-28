import os

import click
from pathlib import Path
from collections import Counter

from asmrcli.core import rj_argument, create_database, id2rj

from logger import logger
from config import config



@click.command()
@click.pass_context
@rj_argument
def play(ctx: click.Context, rj_id: int):
    """play an asmr in the terminal"""
    from database.database import ASMR
    from LRCPlayer import lrc_play
    db = create_database()
    asmr: ASMR | None = db.query(ASMR).get(rj_id)
    if asmr is None:
        logger.error(f'RJ id {rj_id} not found!')
        return
    asmr_rj = id2rj(asmr.id)
    rj_path = Path(config.save_path) / asmr_rj if not asmr.stored else Path(config.storage_path) / asmr_rj

    choices = []
    suf = ['.mp3', '.wav', 'flac']
    for path, folders, files in os.walk(rj_path):
        res = Counter([Path(i).suffix for i in files])
        if not set(res.keys()).intersection(set(suf)):
            continue
        info = ' '.join([f'{key}: {val}' for key, val in res.items() if key in suf])
        print(f'{len(choices)}: {path} with {info}')
        choices.append(path)
    idx = int(input('choose the path to play: '))
    path = Path(choices[idx])

    ctx.invoke(lrc_play, path=path)



