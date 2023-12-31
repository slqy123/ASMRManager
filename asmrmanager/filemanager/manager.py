import os
import shutil
from pathlib import Path
from typing import Iterable, List, Literal, NamedTuple

import toml

from asmrmanager.common.rj_parse import RJID, id2rj, rj2id
from asmrmanager.common.types import PlayListItem
from asmrmanager.filemanager.appdirs_ import (
    CACHE_PATH,
    CONFIG_PATH,
    DATA_PATH,
    LOG_PATH,
)
from asmrmanager.filemanager.file_zipper import zip_chosen_folder
from asmrmanager.logger import logger

# from .exceptions import DstItemAlreadyExistsException, SrcNotExistsException


class FileManager:
    CONFIG_PATH = CONFIG_PATH
    DATA_PATH = DATA_PATH
    LOG_PATH = LOG_PATH
    CACHE_PATH = CACHE_PATH

    @classmethod
    def init_config(cls):
        cls.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        dst_path = cls.CONFIG_PATH / "config.toml"
        if dst_path.exists():
            return

        shutil.copy(
            Path(__file__).parent / "resources" / "config.example.toml",
            dst_path,
        )
        logger.info(
            f"An example config file has been copied to {dst_path}, please"
            " modify it and run this command again"
        )
        exit(0)

    @classmethod
    def init_sqls(cls):
        cls.DATA_PATH.mkdir(parents=True, exist_ok=True)
        dst_path = cls.DATA_PATH / "sqls"
        if dst_path.exists():
            return

        shutil.copytree(
            Path(__file__).parent / "resources" / "sqls.example",
            dst_path,
        )
        logger.info(f"First time to run, copy default sqls to {dst_path}")

    @classmethod
    def init_mpd(cls):
        cls.DATA_PATH.mkdir(parents=True, exist_ok=True)
        cls.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        mpd_data_path = cls.DATA_PATH / "mpd"
        conf = {
            "music_directory": mpd_data_path / "music",
            "pid_file": mpd_data_path / "mpd.pid",
            "db_file": mpd_data_path / "mpd.db",
            "bind_to_address": "localhost",
            "port": 6600,
        }

        conf["music_directory"].mkdir(parents=True, exist_ok=True)

        with open(cls.CONFIG_PATH / "mpd.conf", "w") as f:
            for k, v in conf.items():
                f.write(f'{k} "{v}"\n')

        logger.info(
            "First time to run, genertate default mpd config to"
            f" {cls.CONFIG_PATH}"
        )

    @classmethod
    def get_playlist_cache(cls) -> List[PlayListItem] | None:
        cls.CACHE_PATH.mkdir(parents=True, exist_ok=True)
        dst_path = cls.CACHE_PATH / "playlist.cache"
        if dst_path.exists():
            playlists = toml.load(dst_path)["playlists"]
            return [PlayListItem(**p) for p in playlists]

    @classmethod
    def save_playlist_cache(cls, playlists: List[PlayListItem]):
        cls.CACHE_PATH.mkdir(parents=True, exist_ok=True)
        dst_path = cls.CACHE_PATH / "playlist.cache"
        toml.dump(
            {"playlists": [p.asdict() for p in playlists]},
            dst_path.open(mode="w", encoding="utf-8"),
        )

    def __init__(
        self,
        storage_path: str,
        download_path: str,
        view_path: str,
    ):
        self.storage_path = Path(storage_path).expanduser()
        self.download_path = Path(download_path).expanduser()
        self.view_path = Path(view_path).expanduser()

        self.storage_path_exists = (
            True if os.path.exists(self.storage_path) else False
        )
        self.download_path_exists = (
            True if os.path.exists(self.download_path) else False
        )
        self.view_path_exists = (
            True if os.path.exists(self.view_path) else False
        )

    def could_store(self):
        return self.storage_path_exists and self.download_path_exists

    def store(self, rj_id: RJID, replace=True):
        """sync download path and storage path"""
        # TODO 换用fcp实现？
        assert self.could_store()
        rj_name = id2rj(rj_id)
        if not os.path.exists(self.download_path / rj_name):
            logger.warning(f"item {rj_name} does not exists, skip it")
            return

        # if os.path.exists(self.storage_path / rj_name):
        #     if not exists_ok:
        #         logger.error(f"the item {rj_name} to store already exists!")
        #         raise DstItemAlreadyExistsException

        #     logger.info(f"remove item {rj_name} in storage")
        #     shutil.rmtree(self.storage_path / rj_name)

        logger.info(
            f"move {self.download_path / rj_name} "
            f"to {self.storage_path / rj_name}"
        )

        for root, _, files in os.walk(self.download_path / rj_name):
            dst_root = self.storage_path / Path(root).relative_to(
                self.download_path
            )
            dst_root.mkdir(parents=True, exist_ok=True)
            for file in files:
                src_file = Path(root) / file
                dst_file = dst_root / file

                if dst_file.exists():
                    if not replace:
                        logger.info(f"file {dst_file} already exists, skip it")
                        continue
                    logger.info(f"In replace mode, remove {dst_file}")
                    os.remove(dst_file)

                logger.info(f"move {src_file} to {dst_file}")
                shutil.move(src_file, dst_file)

        shutil.rmtree(self.download_path / rj_name)

        # try:
        #     shutil.copytree(
        #         self.download_path / rj_name,
        #         self.storage_path / rj_name,
        #         copy_function=shutil.copy2,
        #     )
        # except (FileNotFoundError, PermissionError, shutil.Error) as e:
        #     logger.error(
        #         f"moving files error: {e}, terminated, please munually clean"
        #         f" the files at {self.storage_path / rj_name}"
        #     )
        #     exit(-1)

        # try:
        #     shutil.rmtree(self.download_path / rj_name)
        # except (FileNotFoundError, PermissionError, shutil.Error) as e:
        #     logger.error(
        #         f"deleting original files error: {e}, terminated, please"
        #         f" munually clean the files at {self.download_path / rj_name}"
        #     )
        #     exit(-1)

    def store_all(self, replace=True):
        for file in os.listdir(self.download_path):
            rj_id = rj2id(file)
            if rj_id is None:
                logger.warning(f"Ignore invalid file {file} in download path")
                continue
            self.store(rj_id, replace=replace)

    def could_view(self):
        """
        either storage_path or download_path exists ok,
        view path must exists
        """
        return self.view_path_exists and (
            self.storage_path_exists or self.download_path_exists
        )

    @staticmethod
    def link(src: Path, dst: Path, hardlink=False):
        if hardlink:
            os.link(src, dst)
        else:
            os.symlink(src, dst)

    @staticmethod
    def _copy(src: Path, dst: Path, depth: int = -1):
        if src.is_file():
            shutil.copy(src, dst)
            return

        if depth == 0:
            return

        dst.mkdir(parents=True, exist_ok=True)

        for subfile in src.iterdir():
            FileManager._copy(subfile, dst / subfile.name, depth - 1)

    def remove_view(self, rj_id: RJID):
        assert self.could_view()
        rj_name = id2rj(rj_id)

        for path in self.view_path.iterdir():
            if path.stem != rj_name:
                continue
            if path.is_dir() and path.is_symlink():
                os.remove(path)
                return
            elif path.suffix == ".zip":
                os.remove(path)
                return
        else:
            logger.error(f"file {rj_name} not exists")
            return
        # path = self.view_path / rj_name
        # assert path.is_dir() and path.is_symlink()
        # os.remove(path)

    def list_(
        self, path: Literal["download", "view", "storage"]
    ) -> Iterable[RJID]:
        if path == "download":
            p = self.download_path
        elif path == "view":
            p = self.view_path
        elif path == "storage":
            p = self.storage_path
        else:
            logger.error("Invalid path")
            return []

        for name in p.iterdir():
            rj_id = rj2id(name.name)
            if rj_id is None:
                continue
            yield rj_id

    def zip_file(self, src: Path, dst: Path):
        zip_chosen_folder(src, dst)

    def get_location(
        self, rj_id: RJID
    ) -> Literal["download", "storage", None]:
        rj_name = id2rj(rj_id)
        if (self.storage_path / rj_name).exists():
            return "storage"
        if (self.download_path / rj_name).exists():
            return "download"
        return None

    def get_path(self, rj_id: RJID) -> Path | None:
        """get rj file path"""
        res = self.get_location(rj_id)

        match res:
            case "download":
                return self.download_path / id2rj(rj_id)
            case "storage":
                return self.storage_path / id2rj(rj_id)
            case _:
                return None

    def check_exists(self, rel_path: str):
        download, storage = False, False
        download_file_path = self.download_path / rel_path
        storage_file_path = self.storage_path / rel_path
        if download_file_path.exists():
            download = True
        if storage_file_path.exists():
            storage = True
        if (not download) and self.check_wav_flac_duplicate(
            download_file_path
        ):
            download = True
        if (not storage) and self.check_wav_flac_duplicate(storage_file_path):
            storage = True

        return NamedTuple(
            "ExistInfo", [("download", bool), ("storage", bool)]
        )(download, storage)

    @staticmethod
    def check_wav_flac_duplicate(file_path: Path) -> bool:
        """if file duplicate or already exists, return True"""
        if file_path.exists():
            logger.error(
                f"file already exists: {file_path}, please "
                "check for the existence of the download files first"
            )
            return True
        match file_path.suffix.lower():
            case ".wav":
                another_file_path = file_path.with_suffix(".flac")
                if another_file_path.exists():
                    logger.info(f"Detected {file_path} for same flac exists")
                    return True
            case ".flac":
                another_file_path = file_path.with_suffix(".wav")
                if another_file_path.exists():
                    logger.info(f"Detected {file_path} for same wav exists")
                    return True
            case _:
                pass

        return False
