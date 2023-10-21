from pathlib import Path


class Aria2Downloader:
    def __init__(
        self,
        host: str,
        port: int,
        secret: str,
        proxy: str,
    ) -> None:
        import aria2p

        self.client = aria2p.Client(host=host, port=port, secret=secret)
        self.api = aria2p.API(self.client)
        self.options = aria2p.Options(
            self.api,
            {"all-proxy": proxy},
        )
        self.options.all_proxy

    def download(self, url: str, save_path: Path, filename: str):
        self.options.out = filename
        self.options.dir = str(save_path)
        self.options.auto_file_renaming = False
        self.api.add(url, options=self.options)
