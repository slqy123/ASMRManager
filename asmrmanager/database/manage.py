import math
import uuid
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Any, cast

import sqlalchemy.orm
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine, ResultProxy
from sqlalchemy.engine.result import Result
from sqlalchemy.orm import Session, sessionmaker

from asmrmanager.common.rj_parse import (
    id2source_name,
    is_local_source_id,
    source2id,
)
from asmrmanager.common.types import (
    PRIVACY,
    PROGRESS_VALUES,
    LocalSourceID,
    RecoverRecord,
    RemoteSourceID,
)
from asmrmanager.database.orm_type import ASMRInstance
from asmrmanager.logger import logger

from .database import (
    ASMR,
    SCHEMA_VERSION,
    Playlist,
    RecoveryFile,
    Tag,
    VoiceActor,
    bind_engine,
)
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
        engine: Engine | None = None,
        tag_filter: Sequence[str] = (),
    ):
        self.engine = engine or get_engine()
        if not event.contains(
            self.engine, "connect", create_math_functions_on_connect
        ):
            event.listen(self.engine, "connect", create_math_functions_on_connect)
        with self.engine.connect() as connection:
            version = connection.exec_driver_sql("PRAGMA user_version").scalar()
            if version > SCHEMA_VERSION:
                raise ValueError("Database schema is newer than this application.")
        if not inspect(self.engine).has_table("asmr"):
            bind_engine(self.engine)
            with self.engine.begin() as connection:
                connection.exec_driver_sql(
                    f"PRAGMA user_version = {SCHEMA_VERSION}"
                )

        self.tag_filter = set(tag_filter)

        self.session: Session = sessionmaker(self.engine)()
        self.func = QFunc(self.session)

    def check_db_updated(self):
        inspector = inspect(self.engine)
        names = {c["name"] for c in inspector.get_columns("asmr")}
        with self.engine.connect() as connection:
            version = connection.exec_driver_sql("PRAGMA user_version").scalar()
        return (
            version == SCHEMA_VERSION
            and set(ASMR.__table__.columns.keys()).issubset(names)
            and "count" not in names
            and {"playlist", "playlist_work", "recovery_file"}.issubset(
                inspector.get_table_names()
            )
        )

    def check_exists(
        self, source_id: LocalSourceID | RemoteSourceID
    ) -> ASMRInstance | None:
        return (
            self.session.get(ASMR, source_id)
            or self.session.query(ASMR)
            .filter_by(remote_id=source_id)
            .one_or_none()
        )

    @classmethod
    def parse_info(cls, info: dict[str, Any]) -> ASMRInstance:
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
            details=deepcopy(info),
        )

        for actor_info in info["vas"]:
            actor = VoiceActor(**actor_info)
            asmr.vas.append(actor)

        for tag_info in info["tags"]:
            if not tag_info.get("id"):
                continue
            tag = Tag(id=tag_info["id"], name=tag_info["name"])
            translations = tag_info.get("i18n") or {}
            tag.cn_name = translations.get("zh-cn", {}).get("name")
            tag.jp_name = translations.get("ja-jp", {}).get("name")
            tag.en_name = translations.get("en-us", {}).get("name")
            asmr.tags.append(tag)
        return asmr

    def add_info(
        self,
        info: dict[str, Any],
        check: bool = True,
        tag_strategy: str = "common_only",
    ) -> bool:
        """
        add/update info to database and check
        if it has tag in the filter or not,
        return True if should download
        """

        def tag_strategy_filter(tag: dict) -> bool:
            """true if tag should be accepted and stored in database"""
            if tag_strategy == "accept_all":
                return True
            upvote: int = tag["upvote"]
            downvote: int = tag["downvote"]
            voteRank: int = (
                tag["voteRank"] if "voteRank" in tag else upvote - downvote
            )  # voteRank may be missing
            myVote: int = tag["myVote"]
            voteStatus: int = tag["voteStatus"]
            if voteRank != upvote - downvote and voteStatus != 1:
                logger.warning(
                    f"Tag voteRank ({tag}) does not match the difference between upvotes and downvotes."
                )

            common_only = voteStatus == 1
            accept_all = True
            except_rejected = voteStatus in (0, 1)

            res = eval(
                tag_strategy,
                {
                    "upvote": upvote,
                    "downvote": downvote,
                    "voteRank": voteRank,
                    "myVote": myVote,
                    "voteStatus": voteStatus,
                    "common_only": common_only,
                    "accept_all": accept_all,
                    "except_rejected": except_rejected,
                    "tag": tag,
                },
            )
            if not res:
                logger.debug(
                    f"Filtered tag {tag['name']} ({upvote}/{downvote}, common={common_only})."
                )
            return res

        new_tags = list(filter(tag_strategy_filter, info["tags"]))
        pre_filtered_tags = [t for t in info["tags"] if t not in new_tags]
        if pre_filtered_tags:
            logger.info(
                "Filtered tags: %s",
                ", ".join(t["name"] for t in pre_filtered_tags),
            )
        indexed_info = {**info, "tags": new_tags}
        asmr = self.parse_info(indexed_info)
        asmr.details = deepcopy(info)

        self.session.merge(asmr)

        # check for tag filter
        tags = [t["name"] for t in new_tags]

        if filtered_tags := self.tag_filter.intersection(tags):
            if not check:
                logger.warning(
                    f"Continuing to download {asmr.id} despite its filtered tags: "
                    f"{filtered_tags}."
                )
                return True
            logger.info(f"Skipping {asmr.id} because it has filtered tags: {filtered_tags}.")
            return False
        return True

    def update_review(
        self,
        source_id: LocalSourceID,
        star: int | None = None,
        comment: str | None = None,
        update_stored: bool = False,
        progress: str | None = None,
        clear_progress: bool = False,
    ):
        if star is not None and (type(star) is not int or not 0 <= star <= 5):
            raise ValueError("Rating must be an integer between 0 and 5.")
        if progress is not None and progress not in PROGRESS_VALUES:
            raise ValueError("Unknown listening status.")
        if clear_progress and progress is not None:
            raise ValueError("Cannot set and clear listening status together.")
        asmr = self.session.get(ASMR, source_id)
        if asmr is None:
            raise ValueError("Work not found in the local database.")
        if star is not None:
            asmr.star = star
        if comment is not None:
            asmr.comment = comment
        if progress is not None or clear_progress:
            asmr.progress = progress
        if star is not None or comment is not None:
            asmr.last_review = datetime.now(UTC).astimezone().date()
            if update_stored:
                asmr.stored = True
        return asmr

    def save_recovery(
        self, source_id: LocalSourceID, records: list[RecoverRecord]
    ):
        from asmrmanager.common.types import validate_recovery

        records = validate_recovery(records)
        asmr = self.session.get(ASMR, source_id)
        if asmr is None:
            raise ValueError("Work not found in the local database.")
        self.session.query(RecoveryFile).filter_by(work_id=source_id).delete()
        self.session.add_all(
            RecoveryFile(
                work_id=source_id,
                path=record["path"],
                url=record["url"],
                should_download=record["should_download"],
                file_id=record.get("fileId"),
            )
            for record in records
        )
        asmr.recovery_ready = True

    def load_recovery(
        self, source_id: LocalSourceID
    ) -> list[RecoverRecord] | None:
        asmr = self.session.get(ASMR, source_id)
        if asmr is None or not asmr.recovery_ready:
            return None
        return [
            {
                "path": record.path,
                "url": record.url,
                "should_download": record.should_download,
                "fileId": record.file_id,
            }
            for record in self.session.query(RecoveryFile)
            .filter_by(work_id=source_id)
            .order_by(RecoveryFile.path)
        ]

    def list_playlists(self, limit: int | None = None) -> list[Playlist]:
        query = self.session.query(Playlist).order_by(
            Playlist.name, Playlist.id
        )
        if limit is not None:
            if limit < 1:
                raise ValueError("Playlist limit must be positive.")
            query = query.limit(limit)
        return query.all()

    def get_playlist(self, identifier: str | uuid.UUID) -> Playlist:
        try:
            playlist_id = uuid.UUID(str(identifier))
        except ValueError:
            matches = (
                self.session.query(Playlist).filter_by(name=identifier).all()
            )
            if len(matches) > 1:
                ids = ", ".join(str(item.id) for item in matches)
                raise ValueError(
                    f"Multiple local playlists named {identifier!r}; use a local ID: {ids}"
                )
            playlist = matches[0] if matches else None
        else:
            playlist = self.session.get(Playlist, playlist_id)
        if playlist is None:
            raise ValueError(
                f"Local playlist {str(identifier)!r} not found; run asmr pl list."
            )
        return playlist

    def create_playlist(
        self,
        name: str,
        description: str | None = None,
        privacy: PRIVACY = PRIVACY.PRIVATE,
    ) -> Playlist:
        if not name.strip():
            raise ValueError("Playlist name must not be empty.")
        if not isinstance(privacy, PRIVACY):
            raise TypeError("Playlist privacy must be a PRIVACY value.")
        playlist = Playlist(
            id=uuid.uuid4(),
            name=name,
            description=description or "",
            privacy=privacy.value,
            members_complete=True,
        )
        self.session.add(playlist)
        return playlist

    def resolve_local_work(self, source: str) -> ASMR:
        source_id = source2id(source)
        if source_id is None or not 0 < source_id < 5 * 10**8:
            raise ValueError(f"Invalid work ID: {source!r}.")
        if source.startswith(("RJ", "VJ", "BJ")):
            if (
                not is_local_source_id(source_id)
                or id2source_name(LocalSourceID(source_id))[:2] != source[:2]
            ):
                raise ValueError(f"Invalid work ID: {source!r}.")
            work = self.session.get(ASMR, source_id)
        else:
            work = self.check_exists(source_id)
        if work is None:
            raise ValueError(
                f"Work {source!r} not found in the local database."
            )
        return work

    def add_playlist_works(
        self, playlist_id: uuid.UUID, source_ids: Sequence[LocalSourceID]
    ) -> Playlist:
        playlist = self.get_playlist(playlist_id)
        works = []
        for source_id in dict.fromkeys(source_ids):
            work = self.session.get(ASMR, source_id)
            if work is None:
                raise ValueError(
                    f"Work {source_id} not found in the local database."
                )
            works.append(work)
        existing = {work.id for work in playlist.works}
        playlist.works.extend(
            work for work in works if work.id not in existing
        )
        return playlist

    def remove_playlists(self, playlist_ids: Sequence[uuid.UUID]):
        playlists = [
            self.get_playlist(id_) for id_ in dict.fromkeys(playlist_ids)
        ]
        for playlist in playlists:
            self.session.delete(playlist)

    def hold_item(self, source_id: LocalSourceID, comment: str | None):
        if not (asmr := self.check_exists(source_id)):
            logger.error("RJ ID was not found in the database.")
            return

        if asmr.held:
            logger.warning(f"ASMR ID {source_id} is already on hold.")

        asmr.held = True
        if comment is not None:
            comment = f"{datetime.now(UTC).astimezone().date()}: {comment}\n"
            asmr.notes = (asmr.notes or "") + comment

    def execute(self, sql: str) -> ResultProxy | Result:
        return self.session.execute(text(sql))

    def query(self, *args, **kwargs) -> sqlalchemy.orm.Query:
        return cast(sqlalchemy.orm.Query, self.session.query(*args, **kwargs))

    def commit(self):
        self.session.commit()
        logger.debug("Changes committed successfully.")
