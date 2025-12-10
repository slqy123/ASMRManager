import asyncio
from pathlib import Path
import uuid
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Tuple,
    TypeVar,
)
from dataclasses import dataclass
import xxhash

from asmrmanager.common.browse_params import BrowseParams
from asmrmanager.common.output import print_table
from asmrmanager.common.rj_parse import id2source_name, source_name2id
from asmrmanager.common.select import select_multiple
from asmrmanager.common.types import RemoteSourceID, SourceName
from asmrmanager.spider.utils.concurrency import concurrent_rate_limit
from asmrmanager.config import Aria2Config
from asmrmanager.filemanager.manager import FileManager
from asmrmanager.logger import logger
from asmrmanager.spider.asmrapi import ASMRAPI
from asmrmanager.spider.playlist import ASMRPlayListAPI
from asmrmanager.spider.tag import ASMRTagAPI

from .downloader import ASMRDownloadAPI

T = TypeVar("T", bound=Any)
fm = FileManager.get_fm()


class AsyncManager:
    def __init__(self, api: ASMRAPI) -> None:
        self.api = api

    def run(self, *tasks: Awaitable[T]) -> List[T]:
        async def _run():
            async with self.api:
                return await asyncio.gather(*tasks)

        return asyncio.run(_run())


class ASMRDownloadManager(AsyncManager):
    def __init__(
        self,
        name: str,
        password: str,
        proxy: str | None,
        id_should_download: Callable[[RemoteSourceID], bool] | None = None,
        json_should_download: Callable[[Dict[str, Any]], bool] | None = None,
        name_should_download: (
            Callable[[str, Literal["directory", "file"], bool], bool] | None
        ) = None,
        replace=False,
        download_method: Literal["aria2", "idm"] = "idm",
        aria2_config: Aria2Config | None = None,
        limit: int = 4,
    ):
        self.downloader = ASMRDownloadAPI(
            name=name,
            password=password,
            proxy=proxy,
            name_should_download=name_should_download or (lambda *_: True),
            json_should_download=json_should_download or (lambda _: True),
            replace=replace,
            limit=limit,
            download_method=download_method,
            aria2_config=aria2_config,
        )
        super().__init__(self.downloader)
        self.id_should_download = id_should_download or (lambda _: True)

    async def get(self, ids: List[RemoteSourceID]):
        tasks = []
        for id_ in ids:
            if not self.id_should_download(id_):
                logger.info(f"Remote ID: {id_} already exists.")
                continue
            tasks.append(self.downloader.download(id_))
        await asyncio.gather(*tasks)

    async def search(
        self,
        text: str,
        tags: Tuple[str],
        vas: Tuple[str],
        circle: str | None,
        age: str | None,
        lang: str | None,
        no_tags: Tuple[str],
        no_vas: Tuple[str],
        no_age: Tuple[str],
        no_circle: Tuple[str],
        no_lang: Tuple[str],
        rate: Tuple[float | None, float | None],
        sell: Tuple[int | None, int | None],
        price: Tuple[int | None, int | None],
        duration: Tuple[str | None, str | None],
        params: BrowseParams,
        all_: bool,
    ):
        total_pages_to_download = None
        download_all_pages = False
        if params.page == 0:
            download_all_pages = True
            params.page = 1

        filters = []

        filters += [f"$tag:{t}$" for t in tags]
        filters += [f"$-tag:{nt}$" for nt in no_tags]

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

        while True:
            if filters:
                logger.info(f"searching with {filters} {params}")
                search_result = await self.downloader.get_search_result(
                    " ".join(filters).replace("/", "%2F"), params=params.params
                )
            else:
                logger.info(f"list works with {params}")
                search_result = await self.downloader.list(
                    params=params.params
                )
            ids: List[RemoteSourceID] = [
                work["id"] for work in search_result["works"]
            ]

            if all_:
                await self.get(ids)
            else:
                # select RJs
                source_names: List[SourceName] = [
                    work["source_id"] for work in search_result["works"]
                ]
                titles = [work["title"] for work in search_result["works"]]
                indexes = select_multiple(
                    [
                        f"{source_name} | {title}"
                        for source_name, title in zip(source_names, titles)
                    ],
                )
                if not indexes:
                    logger.error("Nothing was selected.")
                else:
                    await self.get([ids[i] for i in indexes])

            if not download_all_pages:
                break
            else:
                if total_pages_to_download is None:
                    total_pages_to_download = (
                        int(search_result["pagination"]["totalCount"])
                        // int(search_result["pagination"]["pageSize"])
                        + 1
                    )
                    logger.info(
                        f"Total pages to download: {total_pages_to_download}"
                    )
                assert (
                    search_result["pagination"]["currentPage"] == params.page
                )
                if params.page >= total_pages_to_download:
                    logger.info("All pages downloaded.")
                    return
                logger.info(
                    f"Downloading progress: {params.page}/{total_pages_to_download}"
                )
                params.page += 1

    async def tag(self, tag_name: str, params: BrowseParams):
        """tag 和 va 一样，都是调用了特殊的search方法"""
        raise NotImplementedError
        tag_res = await self.downloader.tag(tag_name, params=params.params)
        ids = [work["id"] for work in tag_res["works"]]
        await self.get(ids)

    async def va(self, va_name: str, params: BrowseParams):
        """tag 和 va 一样，都是调用了特殊的search方法"""
        raise NotImplementedError
        va_res = await self.downloader.tag(va_name, params=params.params)
        ids = [work["id"] for work in va_res["works"]]
        await self.get(ids)

    async def update(self, ids: List[RemoteSourceID]):
        async def update_one(source_id_: RemoteSourceID):
            voice_info = await self.downloader.get_voice_info(source_id_)
            if voice_info is None:
                logger.error(f"Failed to update {source_id_}.")
                return

            # should_down = self.spider.json_should_download(voice_info)
            # if not should_down:
            #     logger.info(f"stop download {rj_id_}")
            #     return
            save_path = fm.storage_path

            local_source_id = source_name2id(voice_info["source_id"])
            if local_source_id is None:
                logger.error(f"Failded to convert {source_id_} to local id.")
                return
            voice_path = save_path / id2source_name(local_source_id)
            assert voice_path.name == voice_info["source_id"]
            if not voice_path.exists():
                logger.warning(
                    "There are no such files in your storage path for"
                    f" RJ{source_id_}"
                )

            voice_path.mkdir(parents=True, exist_ok=True)
            self.downloader.create_info_file(voice_info, voice_path)

            tracks = await self.downloader.get_voice_tracks(source_id_)
            if tracks is None:
                logger.error(f"Failed to get tracks for {source_id_}.")
                return

            file_list = self.downloader.get_file_list(tracks, voice_path)
            self.downloader.create_recover_file(file_list, voice_path)

        tasks = []
        for rj_id in ids:
            tasks.append(update_one(rj_id))

        await asyncio.gather(*tasks)

    async def get_recommendations(self, page: int = 1):
        res = await self.downloader.get_recommendations(page)
        ids = [work["id"] for work in res["works"]]
        await self.get(ids)

    async def get_popular(self, page: int = 1):
        res = await self.downloader.get_popular(page)
        ids = [work["id"] for work in res["works"]]
        await self.get(ids)


class ASMRPlayListManager(AsyncManager):
    def __init__(
        self, name: str, password: str, proxy: str | None, limit: int = 3
    ):
        self.playlist = ASMRPlayListAPI(
            name=name, password=password, proxy=proxy, limit=limit
        )
        super().__init__(self.playlist)

    async def list(self, num: int = 12, raw: bool = False):
        from asmrmanager.common.output import print_table

        page = 1
        playlists, total = await self.playlist.get_playlists(
            page=page, page_size=num
        )
        logger.info(f"fetching playlists ({len(playlists)}/{total})")
        while num * page < total:
            page += 1
            playlists_, _ = await self.playlist.get_playlists(
                page=page, page_size=num
            )
            playlists += playlists_
            logger.info(f"fetching playlists ({len(playlists)}/{total})")
        print_table(
            titles=["id", "name", "amount", "privacy"],
            rows=[
                (str(p.id), p.name, p.works_count, p.privacy.name)
                for p in playlists
            ],
            raw=raw,
        )

        fm.save_playlist_cache(playlists)

    async def remove(self, pl_ids: List[uuid.UUID]):
        res = await asyncio.gather(*map(self.playlist.delete_playlist, pl_ids))

        if not isinstance(res, list):
            logger.error("Unexpected response type when delete playlists.")
            return
        for r in res:
            if not isinstance(r, dict):
                logger.error("Unexpected response type when delete playlists.")
                return
            if r.get("error"):
                logger.error(f"Error when delete playlists: {r}")
                return
            logger.info(f"Sucessfully delete playlist {r['id']}.")

    async def create(
        self,
        name: str,
        desc: str | None,
        privacy: Literal["PUBLIC", "NON_PUBLIC", "PRIVATE"],
    ):
        from asmrmanager.spider.playlist import PRIVACY

        res = await self.playlist.create_playlist(name, desc, PRIVACY[privacy])
        if not isinstance(res, dict):
            logger.error("Unexpected response type when create playlist.")
            return
        if res.get("error"):
            logger.error(f"Error when creating playlist:{res}")
            return
        logger.info(f"Sucessfully create playlist: {res['id']}.")

        logger.info("Updating local playlist cache...")
        await self.list()

    async def add(self, source_ids: List[RemoteSourceID], pl_id: uuid.UUID):
        res = await self.playlist.add_works_to_playlist(source_ids, pl_id)
        if not isinstance(res, dict):
            logger.error(
                f"Unexpected response type when add works to {pl_id}."
            )
            return
        if res.get("error"):
            logger.error(f"Error when add works to playlist:{res}")
            return
        logger.info(f"Sucessfully add works to playlist {pl_id}.")

    async def show(self, pl_id: uuid.UUID, page_size: int = 12):
        page = 1
        works, total_count = await self.playlist.show_works_in_playlist(
            pl_id, page, page_size
        )
        while page * page_size < total_count:
            page += 1
            works_, _ = await self.playlist.show_works_in_playlist(
                pl_id, page, page_size
            )
            works += works_
            logger.info(
                f"fetching works in playlist {pl_id}: {len(works)}/{total_count}"
            )

        titles = [
            "id",
            "title",
            "circle_name",
            "nsfw",
            "subtitle",
            "dl_count",
            "voice_actors",
        ]
        print_table(
            titles=titles,
            rows=list(
                map(
                    lambda w: (
                        w["source_id"],
                        w["title"],
                        w["circle"]["name"],
                        w["nsfw"],
                        w["has_subtitle"],
                        w["dl_count"],
                        ",".join([va["name"] for va in w["vas"]]),
                    ),
                    works,
                )
            ),
        )


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
    def __init__(
        self, name: str, password: str, proxy: str | None, limit: int = 3
    ) -> None:
        self.api = ASMRTagAPI(name, password, proxy, limit)

    async def get_asmr_tags(self, source_id: RemoteSourceID):
        voice_info = await ASMRDownloadAPI.get_voice_info(self.api, source_id)  # type: ignore
        assert voice_info is not None, "Failed to get voice info."
        return [ASMRTag(**i) for i in voice_info["tags"]]

    async def get_all_tags(self):
        return await self.api.get_all_tags()

    async def attach_tags(self, tag_ids: list[int], source_id: RemoteSourceID):
        resp = await self.api.attach_tags(tag_ids, source_id)
        if isinstance(resp, dict) and resp.get("error"):
            logger.error(
                f"Failed to attach tags to {source_id}: {resp['error']}"
            )
            return
        else:
            logger.info(f"Successfully attach tags to {source_id}.")

    async def vote_tag(
        self,
        tag_id: int,
        source_id: RemoteSourceID,
        action: Literal["up", "down"],
    ):
        resp = await self.api.vote_tag(tag_id, source_id, action)
        if isinstance(resp, dict) and resp.get("error"):
            logger.error(
                f"Failed to vote tag {tag_id} for {source_id}: {resp['error']}"
            )
            return
        else:
            logger.info(
                f"Successfully vote tag {tag_id} {action} for {source_id}."
            )


class ASMRGeneralManager(AsyncManager):
    def __init__(
        self, name: str, password: str, proxy: str | None, limit: int = 3
    ) -> None:
        self.api = ASMRAPI(name, password, proxy, limit)

    @concurrent_rate_limit()
    async def verify(self, file_path: Path, file_id: int) -> bool:
        xxhash_ = xxhash.xxh128_hexdigest(file_path.read_bytes())
        res = await self.api.verify_hash(file_id, xxhash_)
        logger.debug(f"Hash of file {file_id}: {xxhash_}")
        logger.debug(f"Response: {res}")
        res = res["result"]
        if res:
            logger.debug(f"File {file_id} is verified.")
        else:
            logger.error(f"File {file_id} is not verified.")
        return res
