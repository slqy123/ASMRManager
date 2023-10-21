import os
import shutil
from typing import Iterable, Literal, NamedTuple
from pathlib import Path

from asmrmanager.common.rj_parse import RJID, id2rj, rj2id
from config import config
from asmrmanager.filemanager.file_zipper import zip_chosen_folder
from asmrmanager.logger import logger

from .exceptions import DstItemAlreadyExistsException, SrcNotExistsException


class FileManager:
    def __init__(
        self,
        storage_path: str | None = None,
        download_path: str | None = None,
        view_path: str | None = None,
    ):
        self.storage_path = Path(storage_path or config.storage_path)
        self.download_path = Path(download_path or config.download_path)
        self.view_path = Path(view_path or config.view_path)

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

    def view(self, rj_id: RJID, replace=True):
        assert self.could_view()
        rj_name = id2rj(rj_id)
        if os.path.exists(self.storage_path / rj_name):
            src = self.storage_path / rj_name
        elif os.path.exists(self.download_path / rj_name):
            src = self.download_path / rj_name
        else:
            logger.error(f"Failed to view {rj_name}, item not exists!")
            raise SrcNotExistsException

        if os.path.exists(self.view_path / rj_name):
            logger.warning(f"{rj_name} already exists!")
            if not replace:
                raise DstItemAlreadyExistsException

        os.symlink(src, self.view_path / rj_name)

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

    def zip_file(self, rj_id: RJID, stored: bool | None = None):
        assert self.could_view()
        rj_name = id2rj(rj_id)
        if stored is None:
            src1 = self.storage_path / rj_name
            src2 = self.download_path / rj_name
            if src1.exists():
                src = src1
            elif src2.exists():
                src = src2
            else:
                logger.error(f"file {rj_name} not exists, locate file failed")
                raise SrcNotExistsException
        else:
            path = self.storage_path if stored else self.download_path
            src = path / rj_name
            assert src.exists()

        dst = self.view_path / rj_name
        dst = dst.with_suffix(".zip")
        if dst.exists():
            logger.error(f"file {dst} already exists please remove first")
            raise DstItemAlreadyExistsException
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

    def get_path(self, rj_id: RJID):
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


file_manager = FileManager(
    config.storage_path, config.download_path, config.view_path
)
fm = file_manager
