from time import time
from typing import Any, Literal, Optional, TYPE_CHECKING
import click
from click.shell_completion import CompletionItem
import json
import dataclasses


from asmrmanager.cli.core import (
    convert2remote_id,
    rj_argument,
    create_tags_api,
    get_prev_source,
)
from asmrmanager.common.rj_parse import is_remote_source_id, source2id
from asmrmanager.common.types import RemoteSourceID
from asmrmanager.filemanager.appdirs_ import CACHE_PATH
from asmrmanager.logger import logger

if TYPE_CHECKING:
    from asmrmanager.spider.interface import ASMRTag


def get_all_tags() -> list[dict]:
    def fetch_all_tags() -> list[dict]:
        api = create_tags_api()
        return api.run(api.get_all_tags())[0]

    CACHE_PATH.mkdir(parents=True, exist_ok=True)
    tags_cache = CACHE_PATH / "tags.json"

    # skip if modified time is less than 24 hour
    if (
        not tags_cache.exists()
        or time() - tags_cache.stat().st_mtime > 24 * 60 * 60
    ):
        tags = fetch_all_tags()
        with tags_cache.open("w", encoding="utf-8") as f:
            json.dump(
                tags,
                f,
                ensure_ascii=False,
            )
    return json.load(tags_cache.open(encoding="utf-8"))


def get_prev_id():
    source = get_prev_source()
    if source == "":
        logger.error(
            "No previous source id available,"
            " please first run a command with source id"
        )
        exit(-1)

    source_id = source2id(source)
    if source_id is None:
        logger.error(f"Invalid input source id: {source}")
        exit(-1)

    if not is_remote_source_id(source_id):
        source_id = convert2remote_id(source_id)

    if source_id is None:
        logger.error("failed to convert to remote source id")
        exit(-1)

    return RemoteSourceID(source_id)


def get_prev_tags(source_id: RemoteSourceID):
    def fetch_prev_tags() -> list["ASMRTag"]:
        api = create_tags_api()
        return api.run(api.get_asmr_tags(RemoteSourceID(source_id)))[0]

    CACHE_PATH.mkdir(parents=True, exist_ok=True)
    prev_info_cache = CACHE_PATH / "prev_info.json"
    if not prev_info_cache.exists() or (
        json.load(prev_info_cache.open(encoding="utf-8"))["id"] != source_id
    ):
        _prev_tags = fetch_prev_tags()
        with prev_info_cache.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "id": source_id,
                    "tags": list(
                        map(lambda t: dataclasses.asdict(t), _prev_tags)
                    ),
                },
                f,
                ensure_ascii=False,
            )

    return json.load(prev_info_cache.open(encoding="utf-8"))["tags"]


class TagType(click.ParamType):
    name = "tag"

    def __init__(self, mode: Literal["all", "prev", "new"]) -> None:
        super().__init__()
        self.mode = mode

    def convert(
        self,
        value: Any,
        param: Optional["click.Parameter"],
        ctx: Optional["click.Context"],
    ) -> Any:
        assert isinstance(value, str)
        if value.isdigit():
            value = int(value)

        with (CACHE_PATH / "tags.json").open(encoding="utf-8") as f:
            tags = json.load(f)
            for tag in tags:
                if tag["name"] == value or tag["id"] == value:
                    logger.info(f"Selected tag_id={tag['id']}: {tag['name']}")
                    return tag["id"]
            else:
                self.fail(f"Invalid tag name: {value}")

    def shell_complete(
        self, ctx: "click.Context", param: "click.Parameter", incomplete: str
    ) -> list["CompletionItem"]:
        # return [
        #     CompletionItem(i["name"], help=i["id"])
        #     for i in json.load(tags_cache.open(encoding="utf-8"))
        # ]

        prev_id = get_prev_id()
        all_tags = get_all_tags()
        prev_tags = get_prev_tags(prev_id)

        if self.mode == "all":
            return [CompletionItem(i["id"], help=i["name"]) for i in all_tags]
        elif self.mode == "prev":
            return [CompletionItem(i["id"], help=i["name"]) for i in prev_tags]
        elif self.mode == "new":
            return [
                CompletionItem(i["id"], help=i["name"])
                for i in all_tags
                if i["id"] not in map(lambda t: t["id"], prev_tags)
            ]
        else:
            assert False, "Invalid mode"


def choose_tag_interactively(mode: Literal["all", "prev", "new"]) -> int:
    if mode == "all":
        tags = get_all_tags()
    elif mode == "prev":
        prev_id = get_prev_id()
        tags = get_prev_tags(prev_id)
    elif mode == "new":
        prev_id = get_prev_id()
        all_tags = get_all_tags()
        prev_tags = get_prev_tags(prev_id)
        tags = list(
            filter(
                lambda t: t["id"] not in map(lambda t: t["id"], prev_tags),
                all_tags,
            )
        )
    from asmrmanager.common.select import select

    index = select(list(map(lambda t: f"{t['name']}\t{t['id']}", tags)))
    logger.info(f"Selected tag_id={tags[index]['id']}: {tags[index]['name']}")
    return tags[index]["id"]


@click.command("up")
@rj_argument("remote")
@click.option(
    "--tag", "-t", default=None, type=TagType("prev"), help="tag id or name"
)
def vote_up(source_id: RemoteSourceID, tag: int | None):
    """upvote a tag"""
    if tag is None:
        tag = choose_tag_interactively("prev")

    api = create_tags_api()
    api.run(api.vote_tag(tag, source_id, action="up"))


@click.command("down")
@rj_argument("remote")
@click.option(
    "--tag", "-t", default=None, type=TagType("prev"), help="tag id or name"
)
def vote_down(source_id: RemoteSourceID, tag: int | None):
    """down vote a tag"""
    if tag is None:
        tag = choose_tag_interactively("prev")
    api = create_tags_api()
    api.run(api.vote_tag(tag, source_id, action="down"))


@click.command("add")
@rj_argument("remote")
@click.option(
    "--tag", "-t", default=None, type=TagType("new"), help="tag id or name"
)
def vote_add(source_id: RemoteSourceID, tag: int | None):
    """add a new tag"""
    if tag is None:
        tag = choose_tag_interactively("new")
    api = create_tags_api()
    api.run(api.attach_tags([tag], source_id))


@click.group("vote")
def vote():
    """vote tags for a work"""
    pass


vote.add_command(vote_up)
vote.add_command(vote_down)
vote.add_command(vote_add)
