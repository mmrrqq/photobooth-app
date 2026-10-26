import logging
import shutil
from pathlib import Path

from ... import PATH_CAMERA_ORIGINAL, PATH_PROCESSED, PATH_UNPROCESSED, RECYCLE_PATH, TMP_PATH
from ...database.models import Mediaitem

logger = logging.getLogger(__name__)


class Files:
    def __init__(self):
        pass

    def check_representing_files_raise(self, item: Mediaitem):
        if not item.processed.is_file():
            raise FileNotFoundError(f"failed to process {item.id} because representing processed file does not exist: {item.processed}")

    def delete_item(self, mediaitem: Mediaitem, delete_to_recycle_dir: bool = True):
        """delete single item"""

        logger.info(f"request delete files of {mediaitem}")

        if mediaitem.captured_original:
            if delete_to_recycle_dir:
                logger.info(f"moving {mediaitem} to recycle directory")
                mediaitem.captured_original.rename(Path(RECYCLE_PATH, mediaitem.captured_original.name))
            else:
                mediaitem.captured_original.unlink(missing_ok=True)

        for file in [mediaitem.processed]:  # could be extended to other processed versions if any again...
            file.unlink(missing_ok=True)

        logger.info(f"deleted files of {mediaitem}")

    def clear_all(self):
        """delete all images, inclusive thumbnails, ..."""
        try:
            try:
                # for now in v9 removing deprecated unprocessed is kept
                # so clear all removes the not-longer-used unprocessed files also.
                shutil.rmtree(PATH_UNPROCESSED)
            except Exception:
                pass
            for file in Path(PATH_PROCESSED).glob("*.*"):
                file.unlink()
            for file in Path(PATH_CAMERA_ORIGINAL).glob("*.*"):
                file.unlink()
            for item in Path(TMP_PATH).glob("*"):
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

        except Exception as exc:
            logger.exception(exc)
            raise exc

        logger.info("deleted all files for mediaitems")
