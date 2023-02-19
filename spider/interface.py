from .spider import ASMRSpider
from common.browse_params import BrowseParams
import asyncio
from typing import Iterable, Callable, Coroutine

from logger import logger


class ASMRSpiderManager:
    def __init__(self, bind: ASMRSpider, should_download_callback: Callable[[int], bool] = None):
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

    async def search(self, content: str, params: BrowseParams):
        if content:
            search_result = await self.spider.get_search_result(content, params=params.params)
        else:
            search_result = await self.spider.list(params=params.params)
        ids = [work['id'] for work in search_result['works']]
        await self.get(ids)

    async def tag(self, tag_id: int, params: BrowseParams):
        tag_res = await self.spider.tag(tag_id, params=params.params)
        ids = [work['id'] for work in tag_res['works']]
        await self.get(ids)

    async def update_info(self, ids: Iterable[int]):

        async def update_one_info(rj_id_: int):
            rj_info = await self.spider.get_voice_info(rj_id_)
            if err := rj_info.get('error'):
                logger.error(f'Info Error: {err}')
                return
            logger.info(f'Get asmr info id=RJ{rj_id_}')
            self.spider.download_callback(rj_info)
            self.spider.create_info_file(rj_info)

        tasks = []
        for rj_id in ids:
            tasks.append(update_one_info(rj_id))

        await asyncio.gather(*tasks)

    def run(self, *tasks: Coroutine):
        async def _run():
            async with self.spider:
                await asyncio.gather(*tasks)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(_run())
