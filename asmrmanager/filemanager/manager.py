import os
import shutil
from pathlib import Path
from typing import (
    Callable,
    Iterable,
    List,
    Literal,
    NamedTuple,
    Set,
    Tuple,
    overload,
)

import toml

from asmrmanager.common.rj_parse import id2source_name, source_name2id
from asmrmanager.common.types import (
    LocalSourceID,
    PlayListItem,
    RecoverRecord,
    SourceName,
)
from asmrmanager.filemanager.appdirs_ import (
    CACHE_PATH,
    CONFIG_PATH,
    DATA_PATH,
    LOG_PATH,
)
from asmrmanager.logger import logger

# from .exceptions import DstItemAlreadyExistsException, SrcNotExistsException


class FileManager:
    CONFIG_PATH = CONFIG_PATH
    DATA_PATH = DATA_PATH
    LOG_PATH = LOG_PATH
    CACHE_PATH = CACHE_PATH
    __instance = None

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

    def store(
        self,
        source_id: LocalSourceID,
        replace=True,
        hook: Callable[[Path], None] | None = None,
    ):
        """sync download path and storage path"""
        # TODO 换用fcp实现？
        assert self.could_store()
        rj_name = id2source_name(source_id)
        if not os.path.exists(self.download_path / rj_name):
            logger.warning(f"item {rj_name} does not exists, skip it")
            return

        if hook is not None:
            logger.info(f"Execute hook function for: {rj_name}")
            hook(self.download_path / rj_name)

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

    def store_all(
        self, replace=True, hook: Callable[[Path], None] | None = None
    ):
        for file in os.listdir(self.download_path):
            source_id = source_name2id(SourceName(file))
            if source_id is None:
                logger.warning(f"Ignore invalid file {file} in download path")
                continue
            self.store(source_id, replace=replace, hook=hook)

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
            shutil.copyfile(src, dst)
            return

        if depth == 0:
            return

        dst.mkdir(parents=True, exist_ok=True)

        for subfile in src.iterdir():
            FileManager._copy(subfile, dst / subfile.name, depth - 1)

    def remove_view(self, source_id: LocalSourceID):
        assert self.could_view()
        rj_name = id2source_name(source_id)

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
    ) -> Iterable[LocalSourceID]:
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
            rj_id = source_name2id(SourceName(name.name))
            if rj_id is None:
                continue
            yield rj_id

    def zip_file(self, src: Path, dst: Path):
        from asmrmanager.filemanager.file_zipper import zip_chosen_folder

        zip_chosen_folder(src, dst)

    def get_location(
        self,
        source_id: LocalSourceID,
        prefer: Literal["storage", "download"] = "storage",
    ) -> Literal["download", "storage", None]:
        source_name = id2source_name(source_id)
        storage_exists = (self.storage_path / source_name).exists()
        download_exists = (self.download_path / source_name).exists()
        if storage_exists and download_exists:
            return prefer
        if storage_exists:
            return "storage"
        if download_exists:
            return "download"
        return None

    def get_path(
        self,
        source_id: LocalSourceID,
        rel: str = "",
        prefer: Literal["storage", "download"] = "storage",
    ) -> Path | None:
        """get rj file path"""
        source_name = id2source_name(source_id)
        path = f"{source_name}/{rel}"
        res = self.check_exists(path)
        # res = self.get_location(source_id, prefer=prefer)
        if not any(res):
            return None

        # return (
        #     self.download_path / path
        #     if res.__getattribute__(prefer)
        #     else self.storage_path / path
        # )
        if prefer == "download":
            return (
                self.download_path / path
                if res.download
                else self.storage_path / path
            )
        elif prefer == "storage":
            return (
                self.storage_path / path
                if res.storage
                else self.download_path / path
            )
        else:
            raise ValueError("Invalid prefer value")

    def check_exists(self, rel_path: str, check_duplicate=True):
        """rel_path = source_name/rel"""
        download, storage = False, False
        download_file_path = self.download_path / rel_path
        storage_file_path = self.storage_path / rel_path
        if download_file_path.exists():
            download = True
        if storage_file_path.exists():
            storage = True

        if check_duplicate:
            if (not download) and self.check_file_duplicate(
                download_file_path
            ):
                download = True
            if (not storage) and self.check_file_duplicate(storage_file_path):
                storage = True

        return NamedTuple(
            "ExistInfo", [("download", bool), ("storage", bool)]
        )(download, storage)

    @staticmethod
    def check_file_duplicate(file_path: Path) -> bool:
        """if file duplicate or already exists in a different type, return True"""
        if file_path.exists():
            logger.warning(
                f"file already exists: {file_path}, please "
                "check for the existence of the download files first"
            )
            return True

        audio_formats = [".wav", ".flac", ".mp3", ".m4a"]
        if file_path.suffix.lower() in audio_formats:
            for audio_format in audio_formats:
                another_file_path = file_path.with_suffix(audio_format)
                if another_file_path.exists():
                    logger.debug(
                        f"Detected {file_path} duplicated for a same name {audio_format} exists"
                    )
                    return True

        lyrics_formats = [".lrc", ".vtt", ".mp3.vtt", ".wav.vtt"]
        if file_path.suffix.lower() in lyrics_formats:
            file_name = file_path.stem
            for lyrics_format in lyrics_formats:
                another_file_path = file_path.with_name(
                    file_name + lyrics_format
                )
                if another_file_path.exists():
                    logger.info(f"Detected {file_path} for same lyrics exists")
                    return True

        # match file_path.suffix.lower():
        #     case ".wav":
        #         another_file_path = file_path.with_suffix(".flac")
        #         if another_file_path.exists():
        #             logger.info(f"Detected {file_path} for same flac exists")
        #             return True
        #     case ".flac":
        #         another_file_path = file_path.with_suffix(".wav")
        #         if another_file_path.exists():
        #             logger.info(f"Detected {file_path} for same wav exists")
        #             return True
        #     case _:
        #         pass

        return False

    def load_recover(
        self, source_id: LocalSourceID
    ) -> List[RecoverRecord] | None:
        """load recover file of source ID(choose download path first)"""
        recover_path = self.get_path(
            source_id, rel=".recover", prefer="download"
        )
        if recover_path is None:
            logger.error(
                f"item {source_id} does not have recover file, please update this"
                " rj id first"
            )
            return

        import json

        recovers: List[RecoverRecord] = json.loads(
            recover_path.read_text(encoding="utf8")
        )
        return recovers

    def get_all_files(self, source_id: LocalSourceID) -> Set[Path]:
        """get all files of source ID both in download and storage path"""
        source_name = id2source_name(source_id)
        l1 = set(
            [
                i.relative_to(self.download_path / source_name)
                for i in (self.download_path / source_name).rglob("*")
                if not i.is_dir()
            ]
        )
        l2 = set(
            [
                i.relative_to(self.storage_path / source_name)
                for i in (self.storage_path / source_name).rglob("*")
                if not i.is_dir()
            ]
        )
        return l1 | l2

    @classmethod
    def get_fm(cls):
        from asmrmanager.config import config

        if cls.__instance is None:
            cls.__instance = cls(
                config.storage_path, config.download_path, config.view_path
            )
        return cls.__instance
