import logging
import os
import shutil
from typing import BinaryIO, Dict, Tuple

from neveai.config import UPLOAD_DIR
from neveai.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)


class LocalStorageProvider:
    @staticmethod
    def upload_file(
        file: BinaryIO, filename: str, tags: Dict[str, str]
    ) -> Tuple[int, str]:
        file_path = f"{UPLOAD_DIR}/{filename}"
        size = 0
        try:
            with open(file_path, "wb") as output:
                while chunk := file.read(1024 * 1024):
                    output.write(chunk)
                    size += len(chunk)
            if not size:
                raise ValueError(ERROR_MESSAGES.EMPTY_CONTENT)
        except BaseException:
            if os.path.isfile(file_path):
                os.remove(file_path)
            raise
        return size, file_path

    @staticmethod
    def get_file(file_path: str) -> str:
        return file_path

    @staticmethod
    def delete_file(file_path: str) -> None:
        local_path = f"{UPLOAD_DIR}/{file_path.split('/')[-1]}"
        if os.path.isfile(local_path):
            os.remove(local_path)
        else:
            log.warning("File %s not found in local storage.", local_path)

    @staticmethod
    def delete_all_files() -> None:
        if not os.path.exists(UPLOAD_DIR):
            log.warning("Directory %s not found in local storage.", UPLOAD_DIR)
            return

        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception:
                log.exception("Failed to delete %s", file_path)


Storage = LocalStorageProvider()
