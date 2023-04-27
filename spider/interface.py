from .spider import ASMRSpider
from common.browse_params import BrowseParams
import asyncio
from typing import Iterable, Callable, Coroutine, Tuple

from logger import logger


class ASMRSpiderManager:
    def __init__(self, bind: ASMRSpider, should_download_callback: Callable[[int], bool] | None = None):
        self.spider = bind
        self.should_download_callback = should_download_callback or (lambda rj_id: True)

    async def get(self, ids: Iterable[int]):
        tasks = []
        for arg in ids:
            if not self.should_download_callback(arg):
                logger.info(f'RJ{arg} already exists.')
                continue
            tasks.append(self.spider.download(arg))
        await asyncio.gather(*tasks)

    async def search(self, text: str, tags: Tuple[str], vas: Tuple[str], circle: str | None, params: BrowseParams):
        conds = []
        conds += [f'$tag:{t}$' for t in tags]
        conds += [f'$va:{va}$' for va in vas]
        if circle:
            conds.append(f'$circle:{circle}$')
        if text:
            conds.append(text)

        if conds:
            logger.info(f'searching with {conds}', params)
            search_result = await self.spider.get_search_result(' '.join(conds), params=params.params)
        else:
            logger.info(f'list works with', params)
            search_result = await self.spider.list(params=params.params)
        ids = [work['id'] for work in search_result['works']]
        await self.get(ids)

    async def tag(self, tag_name: str, params: BrowseParams):
        """tag 和 va 一样，都是调用了特殊的search方法"""
        tag_res = await self.spider.tag(tag_name, params=params.params)
        ids = [work['id'] for work in tag_res['works']]
        await self.get(ids)

    async def va(self, va_name: str, params: BrowseParams):
        """tag 和 va 一样，都是调用了特殊的search方法"""
        va_res = await self.spider.tag(va_name, params=params.params)
        ids = [work['id'] for work in va_res['works']]
        await self.get(ids)

    async def update(self, ids: Iterable[int]):
        async def update_one(rj_id_: int):
            rj_info = await self.spider.get_voice_info(rj_id_)
            if err := rj_info.get('error'):
                logger.error(f'Info Error: {err}')
                return
            logger.info(f'Get asmr info id=RJ{rj_id_}')
            self.spider.download_callback(rj_info)
            self.spider.create_info_file(rj_info)

        tasks = []
        for rj_id in ids:
            tasks.append(update_one(rj_id))

        await asyncio.gather(*tasks)

    def run(self, *tasks: Coroutine):
        async def _run():
            async with self.spider:
                await asyncio.gather(*tasks)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(_run())
