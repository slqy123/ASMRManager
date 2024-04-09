from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from asmrmanager.database.utils.uuid_sqlite import GUID

Base = declarative_base()


class ASMR(Base):
    __tablename__ = "asmr"
    id = Column(Integer, primary_key=True)
    remote_id = Column(Integer, unique=True)

    title = Column(Text)
    circle_name = Column(Text)  # 对应name字段
    tags = relationship("Tag", secondary="asmrs2tags", backref="asmrs")
    vas = relationship("VoiceActor", secondary="asmrs2vas", backref="asmrs")
    nsfw = Column(Boolean)
    release_date = Column(Date)  # 对应release字段
    price = Column(Integer)
    dl_count = Column(Integer)
    has_subtitle = Column(Boolean)

    star = Column(Integer, default=0)
    count = Column(Integer, default=0)
    comment = Column(Text, default="")

    held = Column(Boolean, default=False)
    stored = Column(Boolean, default=False)


class Tag(Base):
    __tablename__ = "tag"
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(Text)
    jp_name = Column(Text)
    cn_name = Column(Text)
    en_name = Column(Text)

    def __repr__(self):
        return str(self.name)


class ASMRs2Tags(Base):
    __tablename__ = "asmrs2tags"

    asmr_id = Column(Integer, ForeignKey("asmr.id"), primary_key=True)

    tag_id = Column(Integer, ForeignKey("tag.id"), primary_key=True)


class History(Base):
    __tablename__ = "history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    asmr_id = Column(Integer, ForeignKey("asmr.id"))
    asmr = relationship(ASMR, backref="histories")
    date = Column(Date)
    finish = Column(Boolean, default=False)
    # platform = Column(Enum(PLATFORM))
    # domain = Column(Enum(DOMAIN), default=DOMAIN(data.data.domain))


class ASMRs2VAs(Base):
    __tablename__ = "asmrs2vas"
    asmr_id = Column(Integer, ForeignKey("asmr.id"), primary_key=True)
    actor_id = Column(GUID, ForeignKey("voice_actor.id"), primary_key=True)


class VoiceActor(Base):
    __tablename__ = "voice_actor"
    id = Column(GUID, primary_key=True)
    name = Column(Text)

    def __repr__(self):
        return str(self.name)


def bind_engine(engine):
    Base.metadata.create_all(engine)
