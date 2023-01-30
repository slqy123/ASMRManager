from sqlalchemy import Column, Integer, Text, ForeignKey, Date, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from database.utils.uuid_sqlite import GUID

Base = declarative_base()


class ASMR(Base):
    __tablename__ = 'asmr'
    id = Column(Integer, primary_key=True)
    title = Column(Text)
    # domain = Column(Enum(DOMAIN), default=DOMAIN(data.data.domain), primary_key=True)
    circle_name = Column(Text)  # 对应name字段
    tags = relationship('Tag', secondary='asmrs2tags', backref='asmrs')
    vas = relationship('VoiceActor', secondary='asmrs2vas', backref='asmrs')
    nsfw = Column(Boolean)
    release_date = Column(Date)  # 对应release字段
    price = Column(Integer)
    dl_count = Column(Integer)

    star = Column(Integer, default=0)
    count = Column(Integer, default=0)
    comment = Column(Text, default='')

    held = Column(Boolean, default=False)
    has_subtitle = Column(Boolean)


class Tag(Base):
    __tablename__ = 'tag'
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(Text)
    jp_name = Column(Text)
    cn_name = Column(Text)
    en_name = Column(Text)


class ASMRs2Tags(Base):
    __tablename__ = 'asmrs2tags'

    asmr_id = Column(Integer, ForeignKey('asmr.id'), primary_key=True)
    # domain = Column(Enum(DOMAIN), ForeignKey('asmr.domain'), primary_key=True)
    tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)


class History(Base):
    __tablename__ = 'history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    asmr_id = Column(Integer, ForeignKey('asmr.id'))
    asmr = relationship(ASMR, backref='histories')
    date = Column(Date)
    finish = Column(Boolean, default=False)
    # platform = Column(Enum(PLATFORM))
    # domain = Column(Enum(DOMAIN), default=DOMAIN(data.data.domain))


class ASMRs2VAs(Base):
    __tablename__ = 'asmrs2vas'
    asmr_id = Column(Integer, ForeignKey('asmr.id'), primary_key=True)
    actor_id = Column(GUID, ForeignKey('voice_actor.id'), primary_key=True)


class VoiceActor(Base):
    __tablename__ = 'voice_actor'
    id = Column(GUID, primary_key=True)
    name = Column(Text)


def bind_engine(engine):
    Base.metadata.create_all(engine)
