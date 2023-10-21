import asyncio
from typing import Any, Callable, Coroutine, Dict, Iterable, Literal, Tuple

import cutie

from asmrmanager.common.browse_params import BrowseParams
from asmrmanager.common.rj_parse import RJID, id2rj
from asmrmanager.logger import logger

from .spider import ASMRSpider

from config import Aria2Config
from asmrmanager.filemanager import fm


class ASMRSpiderManager:
    def __init__(
        self,
        name: str,
        password: str,
        proxy: str,
        id_should_download: Callable[[RJID], bool] | None = None,
        json_should_download: Callable[[Dict[str, Any]], bool] | None = None,
        name_should_download: Callable[
            [str, Literal["directory", "file"]], bool
        ]
        | None = None,
        replace=False,
        download_method: Literal["aria2", "idm"] = "idm",
        aria2_config: Aria2Config | None = None,
    ):
        self.spider = ASMRSpider(
            name=name,
            password=password,
            proxy=proxy,
            name_should_download=name_should_download or (lambda *_: True),
            json_should_download=json_should_download or (lambda _: True),
            replace=replace,
            download_method=download_method,
            aria2_config=aria2_config,
        )
        self.id_should_download = id_should_download or (lambda _: True)

    async def get(self, ids: Iterable[RJID]):
        tasks = []
        for arg in ids:
            if not self.id_should_download(arg):
                logger.info(f"RJ{arg} already exists.")
                continue
            tasks.append(self.spider.download(arg))
        await asyncio.gather(*tasks)

    async def search(
        self,
        text: str,
        tags: Tuple[str],
        vas: Tuple[str],
        circle: str | None,
        no_tags: Tuple[str],
        no_vas: Tuple[str],
        no_circle: Tuple[str],
        rate: Tuple[float | None, float | None],
        sell: Tuple[int | None, int | None],
        price: Tuple[int | None, int | None],
        params: BrowseParams,
        all_: bool,
    ):
        filters = []

        filters += [f"$tag:{t}$" for t in tags]
        filters += [f"$-tag:{nt}$" for nt in no_tags]

        filters += [f"$va:{va}$" for va in vas]
        filters += [f"$-va:{nva}$" for nva in no_vas]

        filters += [f"$-circle:{nc}$" for nc in no_circle]

        for name, value in (("rate", rate), ("sell", sell), ("price", price)):
            if value[0] is not None:
                filters.append(f"${name}:{value[0]}$")
            if value[1] is not None:
                filters.append(f"$-{name}:{value[1]}$")

        if circle:
            filters.append(f"$circle:{circle}$")
        if text:
            filters.append(text)

        if filters:
            logger.info(f"searching with {filters} {params}")
            search_result = await self.spider.get_search_result(
                " ".join(filters).replace("/", "%2F"), params=params.params
            )
        else:
            logger.info(f"list works with {params}")
            search_result = await self.spider.list(params=params.params)
        ids = [work["id"] for work in search_result["works"]]

        if all_:
            await self.get(ids)
            return

        # select RJs
        titles = [work["title"] for work in search_result["works"]]
        indexes = cutie.select_multiple(
            [f"{id2rj(id_)} | {title}" for id_, title in zip(ids, titles)],
        )
        if not indexes:
            logger.error("Nothing was selected.")
            return

        await self.get([ids[i] for i in indexes])

    async def tag(self, tag_name: str, params: BrowseParams):
        """tag 和 va 一样，都是调用了特殊的search方法"""
        tag_res = await self.spider.tag(tag_name, params=params.params)
        ids = [work["id"] for work in tag_res["works"]]
        await self.get(ids)

    async def va(self, va_name: str, params: BrowseParams):
        """tag 和 va 一样，都是调用了特殊的search方法"""
        va_res = await self.spider.tag(va_name, params=params.params)
        ids = [work["id"] for work in va_res["works"]]
        await self.get(ids)

    async def update(self, ids: Iterable[RJID]):
        async def update_one(rj_id_: RJID):
            voice_info = await self.spider.get_voice_info(rj_id_)

            # should_down = self.spider.json_should_download(voice_info)
            # if not should_down:
            #     logger.info(f"stop download {rj_id_}")
            #     return
            save_path = fm.storage_path

            voice_path = save_path / id2rj(rj_id_)
            if not voice_path.exists():
                logger.warning(
                    f"There are such file in your storage path for RJ{rj_id_}"
                )

            voice_path.mkdir(parents=True, exist_ok=True)
            self.spider.create_info_file(voice_info, voice_path)

            tracks = await self.spider.get_voice_tracks(rj_id_)
            if isinstance(tracks, dict):
                if error_info := tracks.get("error"):
                    logger.error(f"RJ{rj_id_} not found, {error_info}")
                    return
                else:
                    logger.error("Unexpected track type: dict")
                    return

            file_list = self.spider.get_file_list(tracks, voice_path)
            self.spider.create_recover_file(file_list, voice_path)

        tasks = []
        for rj_id in ids:
            tasks.append(update_one(rj_id))

        await asyncio.gather(*tasks)

    def run(self, *tasks: Coroutine):
        async def _run():
            async with self.spider:
                return await asyncio.gather(*tasks)

        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run())
        # return asyncio.run(_run())
