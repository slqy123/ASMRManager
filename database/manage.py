from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Any, Dict, Union
from datetime import date

from .database import *
from .engine import get_engine
from .q_func import QFunc

from logger import logger


class DataBaseManager:
    def __init__(self,
                 engine: Union[Engine, None] = None,
                 ):
        self.engine = engine or get_engine()
        bind_engine(self.engine)

        self.session: Session = sessionmaker(self.engine)()
        self.func = QFunc(self.session)

    def check_exists(self, rj_id: int) -> Union[ASMR, None]:
        return self.session.query(ASMR).get(rj_id)

    def add_info(self, info: Dict[str, Any]):
        asmr = ASMR(
            id=info['id'],
            title=info['title'],
            circle_name=info['name'],
            nsfw=info['nsfw'],
            release_date=date.fromisoformat(info['release']),
            price=info['price'],
            dl_count=info['dl_count'],
            has_subtitle=info['has_subtitle']
        )

        # for vas
        for actor_info in info['vas']:
            actor = VoiceActor(**actor_info)
            asmr.vas.append(actor)

        # for tags
        for tag_info in info['tags']:
            if not tag_info.get('id'):
                continue
            tag = Tag(id=tag_info['id'], name=tag_info['name'])
            tag.cn_name = tag_info['i18n']['zh-cn']['name']
            tag.jp_name = tag_info['i18n']['ja-jp']['name']
            tag.en_name = tag_info['i18n']['en-us']['name']

            asmr.tags.append(tag)

        self.session.merge(asmr)

    def update_review(self, rj_id: int, star: int, comment: str):
        if not (asmr := self.check_exists(rj_id)):
            logger.error('Incorrect RJ ID, no item in database!')
            return

        asmr.count += 1

        if star is not None:
            if (not isinstance(star, int)) or star < 1 or star > 5:
                logger.error('Your star should be a integer between 1 and 5')
                return
            asmr.star = star

        if comment is not None:
            comment = f'{date.today()}: {comment}\n'
            asmr.comment += comment

    def hold_item(self, rj_id: int, comment: str):
        if not (asmr := self.check_exists(rj_id)):
            logger.error('Incorrect RJ ID, no item in database!')
            return

        if asmr.held:
            logger.warning(f'ASMR id={rj_id} has already been held!')

        asmr.held = True
        if comment is not None:
            comment = f'{date.today()}: {comment}\n'
            asmr.comment += comment

    @property
    def query(self):
        return self.session.query

    def commit(self):
        self.session.commit()
        logger.info('successfully committed')
