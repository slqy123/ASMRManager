import json
from pathlib import Path
from typing import Any

import aioaria2


class Aria2Downloader:
    def __init__(
        self,
        proxy: str | None,
    ) -> None:
        self.client: aioaria2.Aria2HttpClient
        # logger.info(f"Connecting to aria2 rpc server: {self.client}")
        # self.api = aria2p.API(self.client)
        # self.options = aria2p.Options(
        #     self.api,
        #     {"all-proxy": proxy}
        # )
        # self.options.auto_file_renaming = False
        self.options: dict[str, Any] = {
            "auto-file-renaming": False,
        }
        if proxy:
            self.options["all-proxy"] = proxy

    async def create_client(self, host: str, port: int, secret: str) -> None:
        self.client = await aioaria2.Aria2HttpClient(
            f"{host}:{port}/jsonrpc",
            token=secret,
            loads=json.loads,
            dumps=json.dumps,
        ).__aenter__()

    async def close_client(self) -> None:
        await self.client.__aexit__(None, None, None)

    async def download(self, url: str, save_path: Path, filename: str):
        download_option = {
            "out": filename,
            "dir": str(save_path),
        }
        await self.client.addUri(
            [url], options={**self.options, **download_option}
        )
