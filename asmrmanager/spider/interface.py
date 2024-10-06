import asyncio
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

from asmrmanager.common.browse_params import BrowseParams
from asmrmanager.common.rj_parse import id2source_name, source_name2id
from asmrmanager.common.select import select_multiple
from asmrmanager.common.types import RemoteSourceID, SourceName
from asmrmanager.config import Aria2Config
from asmrmanager.filemanager.manager import FileManager
from asmrmanager.logger import logger
from asmrmanager.spider.asmrapi import ASMRAPI
from asmrmanager.spider.playlist import ASMRPlayListAPI

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

        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run())


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
    ):
        self.downloader = ASMRDownloadAPI(
            name=name,
            password=password,
            proxy=proxy,
            name_should_download=name_should_download or (lambda *_: True),
            json_should_download=json_should_download or (lambda _: True),
            replace=replace,
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
        no_tags: Tuple[str],
        no_vas: Tuple[str],
        no_age: Tuple[str],
        no_circle: Tuple[str],
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

            if download_all_pages:
                await self.get(ids)
            elif all_:
                await self.get(ids)
                return

            if not download_all_pages:
                break
            elif total_pages_to_download is None:
                total_pages_to_download = (
                    int(search_result["pagination"]["totalCount"])
                    // int(search_result["pagination"]["pageSize"])
                    + 1
                )
                logger.info(
                    f"Total pages to download: {total_pages_to_download}"
                )
            else:
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
            return

        await self.get([ids[i] for i in indexes])

    async def tag(self, tag_name: str, params: BrowseParams):
        """tag 和 va 一样，都是调用了特殊的search方法"""
        tag_res = await self.downloader.tag(tag_name, params=params.params)
        ids = [work["id"] for work in tag_res["works"]]
        await self.get(ids)

    async def va(self, va_name: str, params: BrowseParams):
        """tag 和 va 一样，都是调用了特殊的search方法"""
        va_res = await self.downloader.tag(va_name, params=params.params)
        ids = [work["id"] for work in va_res["works"]]
        await self.get(ids)

    async def update(self, ids: List[RemoteSourceID]):
        async def update_one(source_id_: RemoteSourceID):
            voice_info = await self.downloader.get_voice_info(source_id_)

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
            if isinstance(tracks, dict):
                if error_info := tracks.get("error"):
                    logger.error(f"RJ{source_id_} not found, {error_info}")
                    return
                else:
                    logger.error("Unexpected track type: dict")
                    return

            file_list = self.downloader.get_file_list(tracks, voice_path)
            self.downloader.create_recover_file(file_list, voice_path)

        tasks = []
        for rj_id in ids:
            tasks.append(update_one(rj_id))

        await asyncio.gather(*tasks)


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

        playlists, total = await self.playlist.get_playlists(
            page=1, page_size=num
        )
        print_table(
            titles=["id", "name", "amount", "privacy"],
            rows=[
                (str(p.id), p.name, p.works_count, p.privacy.name)
                for p in playlists
            ],
            raw=raw,
        )
        print(f"({len(playlists)}/{total})")

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
