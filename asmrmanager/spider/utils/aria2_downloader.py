import json
from pathlib import Path
from typing import Any

import aioaria2


class Aria2Downloader:
    def __init__(
        self,
        proxy: str | None,
    ) -> None:
        self.client: aioaria2.Aria2HttpClient | None = None
        self.options: dict[str, Any] = {
            "auto-file-renaming": False,
        }
        if proxy:
            self.options["all-proxy"] = proxy

    async def create_client(self, host: str, port: int, secret: str) -> None:
        if self.client is not None:
            raise RuntimeError("aria2 RPC client is already open.")
        client = aioaria2.Aria2HttpClient(
            f"{host}:{port}/jsonrpc",
            token=secret,
            loads=json.loads,
            dumps=json.dumps,
        )
        try:
            self.client = await client.__aenter__()
        except BaseException:
            await client.__aexit__(None, None, None)
            raise

    async def close_client(self) -> None:
        client, self.client = self.client, None
        if client is not None:
            await client.__aexit__(None, None, None)

    async def download(self, url: str, save_path: Path, filename: str) -> None:
        client = self.client
        if client is None:
            raise RuntimeError("aria2 RPC client is not open.")
        download_option = {
            "out": filename,
            "dir": str(save_path),
        }
        res = await client.addUri(
            [url], options={**self.options, **download_option}
        )
        if not isinstance(res, str) or len(res) != 16:
            raise RuntimeError(f"Invalid aria2 submission response: {res!r}.")
