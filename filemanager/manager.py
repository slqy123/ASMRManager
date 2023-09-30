import os
import shutil
from typing import Iterable, Literal
from pathlib import Path

from common.rj_parse import RJID, RJName, id2rj, rj2id
from config import config
from filemanager.file_zipper import zip_chosen_folder
from logger import logger

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

    def store(self, rj_id: RJID, exists_ok: bool = False):
        assert self.could_store()
        rj_name = id2rj(rj_id)
        if not os.path.exists(self.download_path / rj_name):
            logger.warning(f'item {rj_name} does not exists')
            return

        if os.path.exists(self.storage_path / rj_name):
            if not exists_ok:
                logger.error(f'the item {rj_name} to store already exists!')
                raise DstItemAlreadyExistsException

            logger.info(f'remove item {rj_name} in storage')
            shutil.rmtree(self.storage_path / rj_name)

        logger.info(
            f'move {self.download_path / rj_name} '
            f'to {self.storage_path / rj_name}'
        )

        try:
            shutil.copytree(
                self.download_path / rj_name,
                self.storage_path / rj_name,
                copy_function=shutil.copy2,
            )
        except (FileNotFoundError, PermissionError, shutil.Error) as e:
            logger.error(
                f'moving files error: {e}, terminated, '
                f'please munually clean the files at {self.storage_path / rj_name}'
            )
            exit(-1)

        try:
            shutil.rmtree(self.download_path / rj_name)
        except (FileNotFoundError, PermissionError, shutil.Error) as e:
            logger.error(
                f'deleting original files error: {e}, terminated, '
                f'please munually clean the files at {self.download_path / rj_name}'
            )
            exit(-1)

    def store_all(self, exists_ok: bool = False):
        for file in os.listdir(self.download_path):
            rj_id = rj2id(file)
            if rj_id is None:
                logger.warning(f'Ignore invalid file {file} in download path')
                continue
            self.store(rj_id, exists_ok=exists_ok)

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
            logger.error(f'Failed to view {rj_name}, item not exists!')
            raise SrcNotExistsException

        if os.path.exists(self.view_path / rj_name):
            logger.warning(f'{rj_name} already exists!')
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
            elif path.suffix == '.zip':
                os.remove(path)
                return
        else:
            logger.error(f'file {rj_name} not exists')
            return
        # path = self.view_path / rj_name
        # assert path.is_dir() and path.is_symlink()
        # os.remove(path)

    def list_(
        self, path: Literal['download', 'view', 'storage']
    ) -> Iterable[RJID]:
        if path == 'download':
            p = self.download_path
        elif path == 'view':
            p = self.view_path
        elif path == 'storage':
            p = self.storage_path
        else:
            logger.error('Invalid path')
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
                logger.error(f'file {rj_name} not exists, locate file failed')
                raise SrcNotExistsException
        else:
            path = self.storage_path if stored else self.download_path
            src = path / rj_name
            assert src.exists()

        dst = self.view_path / rj_name
        dst = dst.with_suffix('.zip')
        if dst.exists():
            logger.error(f'file {dst} already exists please remove first')
            raise DstItemAlreadyExistsException
        zip_chosen_folder(src, dst)

    def get_location(
        self, rj_id: RJID
    ) -> Literal['download', 'storage', None]:
        rj_name = id2rj(rj_id)
        if (self.download_path / rj_name).exists():
            return 'download'
        if (self.storage_path / rj_name).exists() and self.could_store():
            return 'storage'
        return None


file_manager = FileManager(
    config.storage_path, config.download_path, config.view_path
)
fm = file_manager
