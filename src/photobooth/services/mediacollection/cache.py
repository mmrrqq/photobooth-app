import logging
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from ... import CACHE_PATH
from ...appconfig import appconfig
from ...database.database import engine
from ...database.models import Cacheditem, DimensionTypes, Mediaitem
from ...utils.media_resizer import resize
from ...utils.metrics_timer import MetricsTimer

logger = logging.getLogger(__name__)


class Cache:
    def __init__(self):
        self._lock_cache_check: Lock = Lock()

    def get_cached_repr(self, item: Mediaitem, dimension: DimensionTypes, processed: bool = True) -> Cacheditem:
        dimension_pixel = getattr(appconfig.mediaprocessing, f"{dimension}_still_length", None)

        if not item.id:
            raise ValueError("there is no item.id given - cannot create cached representation without id!")
        if dimension_pixel is None:
            raise ValueError(f"invalid dimension given: '{dimension}'")

        with Session(engine) as session:
            # if there are multiple requests for same item at the same time,
            # it might lead to generate cached versions multiple times wasting cpu until it's done.
            # so it's locked from the moment it's checked but that means there is only one process
            # at a time. Maybe a queue is more efficient, but it's ok for now probably.
            with self._lock_cache_check:
                cacheditem_exists = self._db_check_cache_valid(item.id, dimension, processed)

                if cacheditem_exists:
                    return cacheditem_exists

                else:
                    id = uuid4()
                    file_in = item.processed if processed else item.captured_original
                    file_out_stem = f"{id.hex}_{'proc' if processed else 'unproc'}_{dimension}"

                    # this should not happen, because there is no way to apply filters or similar to a mediaitem that has no original
                    # for example collages have no captured original but only processed full because it is generated from several originals.
                    assert file_in is not None, "no captured_original but requested to resize"

                    cacheditem_new = Cacheditem(
                        id=id,
                        mediaitem_id=item.id,
                        dimension=dimension,
                        processed=processed,
                        revision=item.revision,
                        filepath=Path(CACHE_PATH, file_out_stem).with_suffix(item.processed.suffix),
                    )

                    with MetricsTimer(f"generate resized '{dimension}' for {cacheditem_new.filepath}"):
                        resize(
                            filepath_in=file_in,
                            filepath_out=cacheditem_new.filepath,
                            scaled_min_length=dimension_pixel,
                        )

                    session.add(cacheditem_new)
                    session.commit()
                    session.refresh(cacheditem_new)  # refresh so consuming function can access the attributes in cacheditem_new without session

                    return cacheditem_new

    def _db_check_cache_valid(self, mediaitem_id: UUID, dimension: DimensionTypes, processed: bool = True):
        with Session(engine) as session:
            stmt = (
                select(Cacheditem)
                .join(Mediaitem)
                .where(
                    Cacheditem.mediaitem_id == mediaitem_id,
                    Cacheditem.dimension == dimension,
                    Cacheditem.processed == processed,
                    or_(  # for cache we need to check the revision only in processed variant because the original will always remain the same
                        Cacheditem.processed.is_(False),  # if == False, next line is skipped and revision is not relevant for cache existence
                        Mediaitem.revision == Cacheditem.revision,
                    ),
                )
            )

            cacheditem_exists = session.scalars(stmt).one_or_none()  # if none, there is no item yet cached and cached version needs to be created.

            # check files also, otherwise delete the item:
            if cacheditem_exists and not cacheditem_exists.filepath.exists():
                logger.warning("deleting cached item from DB because file representation does not exist any more.")
                session.delete(cacheditem_exists)
                session.commit()

                return None

            return cacheditem_exists

    def on_start_maintain(self):
        outdated_filepaths: list[Path] = []

        with Session(engine) as session:
            statement = (
                select(Cacheditem)
                .join(Mediaitem)
                .where(
                    and_(  # items can be outdated only if processed is true (unprocessed never change) and revision is different.
                        Cacheditem.processed.is_(True),
                        Mediaitem.revision != Cacheditem.revision,
                    )
                )
            )
            results = session.scalars(statement)
            outdated_items = results.all()

            for outdated_item in outdated_items:
                outdated_filepaths.append(outdated_item.filepath)
                session.delete(outdated_item)

            session.commit()

            logger.debug(f"deleted {len(outdated_items)} outdated items from the cache")

            for outdated_filepath in outdated_filepaths:
                try:
                    outdated_filepath.unlink()
                except Exception as exc:
                    logger.warning(f"could not delete file {outdated_filepath} from cache, error: {exc}")

    def clear_all(self):
        self.db_clear_all()
        self.fs_clear_all()

    def db_clear_all(self):
        with Session(engine) as session:
            statement = delete(Cacheditem)
            session.execute(statement)
            session.commit()

    def fs_clear_all(self):
        for file in Path(f"{CACHE_PATH}").glob("*.*"):
            file.unlink()

        logger.info("deleted all files for mediaitems")
