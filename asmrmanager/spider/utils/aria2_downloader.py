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

    async def download(self, url: str, save_path: Path, filename: str) -> None:
        download_option = {
            "out": filename,
            "dir": str(save_path),
        }
        res = await self.client.addUri(
            [url], options={**self.options, **download_option}
        )
        if not isinstance(res, str) or len(res) != 16:
            raise RuntimeError(f"Invalid aria2 submission response: {res!r}.")
