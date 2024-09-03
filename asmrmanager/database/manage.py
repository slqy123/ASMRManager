import math
from datetime import date
from typing import Any, Dict, Sequence, Union, cast

import sqlalchemy.orm
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, ResultProxy
from sqlalchemy.engine.result import Result
from sqlalchemy.orm import Session, sessionmaker

from asmrmanager.common.rj_parse import is_local_source_id, source2id
from asmrmanager.common.types import LocalSourceID, RemoteSourceID
from asmrmanager.database.orm_type import ASMRInstance
from asmrmanager.logger import logger

from .database import ASMR, Tag, VoiceActor, bind_engine
from .engine import get_engine
from .q_func import QFunc


def create_math_functions_on_connect(dbapi_connection, connection_record):
    dbapi_connection.create_function("sin", 1, math.sin)
    dbapi_connection.create_function("cos", 1, math.cos)
    dbapi_connection.create_function("acos", 1, math.acos)
    dbapi_connection.create_function("radians", 1, math.radians)
    dbapi_connection.create_function("log2", 1, math.log2)
    dbapi_connection.create_function("log10", 1, math.log10)


class DataBaseManager:
    def __init__(
        self,
        engine: Union[Engine, None] = None,
        tag_filter: Sequence[str] = tuple(),
    ):
        global create_math_functions_on_connect
        self.engine = engine or get_engine()
        event.listens_for(self.engine, "connect")(
            create_math_functions_on_connect
        )  # add a listener after engine created, before session created
        bind_engine(self.engine)

        self.tag_filter = set(tag_filter)

        self.session: Session = sessionmaker(self.engine)()
        self.func = QFunc(self.session)

    def check_db_updated(self):
        from sqlalchemy import inspect

        inspector = inspect(self.engine)
        columns = inspector.get_columns("asmr")
        names = [c["name"] for c in columns]
        return "remote_id" in names

    def check_exists(
        self, source_id: LocalSourceID | RemoteSourceID
    ) -> Union[ASMRInstance, None]:
        return (
            self.session.query(ASMR).get(source_id)
            or self.session.query(ASMR)
            .filter_by(remote_id=source_id)
            .one_or_none()
        )

    @classmethod
    def parse_info(cls, info: Dict[str, Any]) -> ASMRInstance:
        source = info.get("source_id")
        assert isinstance(source, str)
        source_id = source2id(source)
        assert source_id is not None
        assert is_local_source_id(source_id)
        asmr = ASMR(
            id=source_id,
            remote_id=info["id"],
            title=info["title"],
            circle_name=info["name"],
            nsfw=info["nsfw"],
            release_date=date.fromisoformat(info["release"]),
            price=info["price"],
            dl_count=info["dl_count"],
            has_subtitle=info["has_subtitle"],
        )

        for actor_info in info["vas"]:
            actor = VoiceActor(**actor_info)
            asmr.vas.append(actor)

        for tag_info in info["tags"]:
            if not tag_info.get("id"):
                continue
            tag = Tag(id=tag_info["id"], name=tag_info["name"])
            if tag_info["i18n"]:
                tag.cn_name = tag_info["i18n"]["zh-cn"]["name"]
                tag.jp_name = tag_info["i18n"]["ja-jp"]["name"]
                tag.en_name = tag_info["i18n"]["en-us"]["name"]
            else:
                # assert tag.id == 10000
                assert getattr(tag, "id") == 10000
            asmr.tags.append(tag)
        return asmr

    def add_info(self, info: Dict[str, Any], check: bool = True) -> bool:
        """
        add/update info to database and check
        if it has tag in the filter or not,
        return True if should download
        """

        asmr = self.parse_info(info)

        self.session.merge(asmr)

        # check for tag filter
        tags = [t["name"] for t in info["tags"]]

        if self.tag_filter.intersection(tags):
            if not check:
                logger.warning(
                    f"Continue to download {asmr.id} though it has tags:"
                    f" {tags}"
                )
                return True
            logger.info(f"ignore {asmr.id} since it has tags: {tags}")
            return False
        return True

    def update_review(
        self,
        source_id: LocalSourceID,
        star: int,
        comment: str,
        update_stored: bool = False,
    ):
        if not (asmr := self.check_exists(source_id)):
            logger.error("Incorrect RJ ID, no item in database!")
            exit(-1)

        asmr.count += 1

        if star is not None:
            if (not isinstance(star, int)) or star < 1 or star > 5:
                logger.error("Your star should be a integer between 1 and 5")
                exit(-1)
            asmr.star = star

        if comment is not None:
            comment = f"{date.today()}: {comment}\n"
            asmr.comment += comment

        if update_stored:
            asmr.stored = True

    def hold_item(self, source_id: LocalSourceID, comment: str | None):
        if not (asmr := self.check_exists(source_id)):
            logger.error("Incorrect RJ ID, no item in database!")
            return

        if asmr.held:
            logger.warning(f"ASMR id={source_id} has already been held!")

        asmr.held = True
        if comment is not None:
            comment = f"{date.today()}: {comment}\n"
            asmr.comment += comment

    def execute(self, sql: str) -> ResultProxy | Result:
        return self.session.execute(text(sql))

    def query(self, *args, **kwargs) -> sqlalchemy.orm.Query:
        return cast(sqlalchemy.orm.Query, self.session.query(*args, **kwargs))

    def commit(self):
        self.session.commit()
        logger.info("successfully committed")
