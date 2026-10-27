import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

import xxhash

from asmrmanager.common.browse_params import BrowseParams
from asmrmanager.common.rj_parse import source_name2id
from asmrmanager.common.types import (
    LocalSourceID,
    RecoverRecord,
    RemoteSourceID,
)
from asmrmanager.config import Aria2Config
from asmrmanager.filemanager.manager import FileManager
from asmrmanager.logger import logger
from asmrmanager.spider.asmrapi import ASMRAPI, APIError
from asmrmanager.spider.auth import AuthenticationError

from .downloader import ASMRDownloader, BackendError

fm = FileManager.get_fm()


class AsyncManager:
    def __init__(self, api: ASMRAPI) -> None:
        self.api = api

    async def __aenter__(self) -> Self:
        await self.api.__aenter__()
        return self

    async def __aexit__(self, *args) -> None:
        await self.api.__aexit__(*args)

    async def gather[T](self, *tasks: Awaitable[T]) -> list[T]:
        pending: list[asyncio.Future[T]] = []
        try:
            for task in tasks:
                pending.append(asyncio.ensure_future(task))
            return await asyncio.gather(*pending)
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise

    def run[T](self, *tasks: Awaitable[T]) -> list[T]:
        async def run() -> list[T]:
            async with self:
                return await self.gather(*tasks)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(run())

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, run()).result()

    async def get_cover_path(self, work: Any):
        remote_id, source_name = work["id"], work["source_id"]
        path = fm.get_cover_path(source_name2id(source_name))
        if path.name != "akarin.jpg":
            logger.debug("Using cached cover for %s", source_name)
            return str(path)
        save_path = fm.CACHE_PATH.joinpath("covers").joinpath(
            f"{source_name}.jpg"
        )
        save_path.parent.mkdir(exist_ok=True, parents=True)
        image_data = await self.api.get_cover(remote_id)
        with save_path.open("wb") as f:
            f.write(image_data)
        return str(save_path)


class ASMRDownloadManager(AsyncManager):
    def __init__(
        self,
        api: ASMRAPI,
        id_should_download: Callable[[RemoteSourceID], bool] | None = None,
        json_should_download: Callable[[dict[str, Any]], bool] | None = None,
        name_should_download: (
            Callable[[str, Literal["directory", "file"]], int] | None
        ) = None,
        replace=False,
        download_method: Literal["aria2", "idm"] = "idm",
        aria2_config: Aria2Config | None = None,
        fetch_cover: bool = False,
        tagger: Literal["tag", "tagw"] = "tag",
        save_recovery: Callable[[LocalSourceID, list[RecoverRecord]], None] | None = None,
    ):
        super().__init__(api)
        self.downloader = ASMRDownloader(
            api=self.api,
            name_should_download=name_should_download or (lambda *_: True),
            json_should_download=json_should_download or (lambda _: True),
            replace=replace,
            download_method=download_method,
            aria2_config=aria2_config,
            fetch_cover=fetch_cover,
            save_recovery=save_recovery,
        )
        self.id_should_download = id_should_download or (lambda _: True)
        self.tagger = tagger

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        try:
            await self.downloader.__aenter__()
        except BaseException:
            await super().__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *args) -> None:
        try:
            await self.downloader.__aexit__(*args)
        finally:
            await super().__aexit__(*args)

    async def _process_works(
        self,
        ids: list[RemoteSourceID],
        process: Callable[[RemoteSourceID], Awaitable[None]],
    ) -> list[RemoteSourceID]:
        pending_ids = iter(enumerate(ids))
        failed_ids: dict[int, RemoteSourceID] = {}

        async def worker() -> None:
            for index, source_id in pending_ids:
                try:
                    await process(source_id)
                except (ModuleNotFoundError, BackendError, AuthenticationError):
                    raise
                except Exception as exc:
                    logger.error("Failed to process work %d: %s", source_id, exc)
                    failed_ids[index] = source_id

        await self.gather(
            *(worker() for _ in range(min(len(ids), self.api.transport.limit)))
        )
        return [failed_ids[index] for index in sorted(failed_ids)]

    async def get(self, ids: list[RemoteSourceID]) -> list[RemoteSourceID]:
        ids_to_download = []
        for id_ in ids:
            if not self.id_should_download(id_):
                logger.info(f"Remote ID: {id_} already exists.")
                continue
            ids_to_download.append(id_)
        return await self._process_works(ids_to_download, self.downloader.download)

    async def search(
        self,
        text: str,
        tags: tuple[str],
        vas: tuple[str],
        circle: str | None,
        age: str | None,
        lang: str | None,
        no_tags: tuple[str],
        no_vas: tuple[str],
        no_age: tuple[str],
        no_circle: tuple[str],
        no_lang: tuple[str],
        rate: tuple[float | None, float | None],
        sell: tuple[int | None, int | None],
        price: tuple[int | None, int | None],
        duration: tuple[str | None, str | None],
        params: BrowseParams,
    ) -> dict[str, Any]:
        filters = []

        filters += [f"${self.tagger}:{t}$" for t in tags]
        filters += [f"$-{self.tagger}:{nt}$" for nt in no_tags]

        filters += [f"$va:{va}$" for va in vas]
        filters += [f"$-va:{nva}$" for nva in no_vas]

        filters += [f"$-circle:{nc}$" for nc in no_circle]
        filters += [f"$-age:{na}$" for na in no_age]
        filters += [f"$-lang:{nl}$" for nl in no_lang]

        for name, value in (
            ("rate", rate),
            ("sell", sell),
            ("price", price),
            ("duration", duration),
        ):
            if value[0] is not None:
                filters.append(f"${name}:{value[0]}$")
            if value[1] is not None:
                filters.append(f"$-{name}:{value[1]}$")

        if circle:
            filters.append(f"$circle:{circle}$")
        if age:
            filters.append(f"$age:{age}$")
        if lang:
            filters.append(f"$lang:{lang}$")
        if text:
            filters.append(text)

        if filters:
            logger.info(f"Searching with {filters} {params}")
            return await self.api.get_search_result(
                " ".join(filters).replace("/", "%2F"), params=params.params
            )
        logger.info(f"List works with {params}")
        return await self.api.list(params=params.params)

    async def update(self, ids: list[RemoteSourceID]) -> list[RemoteSourceID]:
        return await self._process_works(ids, self.downloader.update)

    async def get_recommendations(self, page: int = 1) -> list[RemoteSourceID]:
        res = await self.api.get_recommendations(page)
        ids = [work["id"] for work in res["works"]]
        return await self.get(ids)

    async def get_popular(self, page: int = 1) -> list[RemoteSourceID]:
        res = await self.api.get_popular(page)
        ids = [work["id"] for work in res["works"]]
        return await self.get(ids)


@dataclass
class ASMRTag:
    id: int
    name: str
    myVote: int
    downvote: int
    upvote: int
    voteRank: int
    voteStatus: int
    i18n: dict[
        Literal["en-us", "ja-jp", "zh-cn"],
        dict[Literal["name", "history"], Any],
    ]


class ASMRTagManager(AsyncManager):
    async def get_asmr_tags(self, source_id: RemoteSourceID):
        voice_info = await self.api.get_voice_info(source_id)
        if voice_info is None:
            raise APIError(f"Failed to get info for work {source_id}.")
        return [ASMRTag(**i) for i in voice_info["tags"]]

    async def get_all_tags(self):
        return await self.api.get_all_tags()

    async def attach_tags(self, tag_ids: list[int], source_id: RemoteSourceID):
        await self.api.attach_tags(tag_ids, source_id)
        logger.info("Attached tags to source %s.", source_id)

    async def vote_tag(
        self,
        tag_id: int,
        source_id: RemoteSourceID,
        action: Literal["up", "down"],
    ):
        await self.api.vote_tag(tag_id, source_id, action)
        logger.info(
            "Voted %s on tag %s for source %s.",
            action,
            tag_id,
            source_id,
        )


class ASMRGeneralManager(AsyncManager):
    async def verify(self, file_path: Path, file_id: int) -> bool:
        xxhash_ = xxhash.xxh128_hexdigest(file_path.read_bytes())
        res = await self.api.verify_hash(file_id, xxhash_)
        logger.debug("Hash for file %s: %s", file_id, xxhash_)
        logger.debug(f"Response: {res}")
        res = res["result"]
        if res:
            logger.debug("Verified file %s successfully.", file_id)
        else:
            logger.error("Verification failed for file %s.", file_id)
        return res
