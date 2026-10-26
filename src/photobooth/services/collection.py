"""
Handle all media collection related functions
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from ..appconfig import appconfig
from ..database.database import engine
from ..database.models import Mediaitem
from ..database.schemas import MediaitemPublic
from ..plugins import pm as pluggy_pm
from .base import BaseService
from .mediacollection.cache import Cache
from .mediacollection.database import Database
from .mediacollection.files import Files
from .sse import sse_service
from .sse.sse_ import SseEventDbInsert, SseEventDbRemove, SseEventDbUpdate

logger = logging.getLogger(__name__)


class MediacollectionService(BaseService):
    """Handle all image related stuff"""

    def __init__(self):
        super().__init__()

        self.cache: Cache = Cache()
        self.db: Database = Database()
        self.fs: Files = Files()

        # don't access database during init because it might not be set up during tests...

    def start(self):
        super().start()

        self.on_start_maintain()

        logger.info(f"initialized DB, found {self.count()} images")

        super().started()

    def stop(self):
        super().stop()

        super().stopped()

    def on_start_maintain(self):
        # remove outdated items from cache during startup.
        self.cache.on_start_maintain()

    def add_item(self, item: Mediaitem):
        # check files are avail:
        self.fs.check_representing_files_raise(item)

        self.db.add_item(item)

        # if shown in gallery negative priority_modifier for higher prio.
        pluggy_pm.hook.collection_files_added(files=[item.processed], priority_modifier=-1 if item.show_in_gallery else +1)

        if item.captured_original:
            pluggy_pm.hook.collection_files_added(files=[item.captured_original], priority_modifier=+2)

        # and insert in client db collection so gallery is up to date.
        if item.show_in_gallery:
            sse_service.dispatch_event(SseEventDbInsert(mediaitem=MediaitemPublic.model_validate(item)))

        return item.id

    def update_item(self, item: Mediaitem):
        self.fs.check_representing_files_raise(item)

        self.db.update_item(item)

        pluggy_pm.hook.collection_files_updated(files=[item.processed])

        # send update not to clients, so they can load updated images in case needed.
        sse_service.dispatch_event(SseEventDbUpdate(mediaitem=MediaitemPublic.model_validate(item)))

    def delete_item(self, item: Mediaitem):
        self.db.delete_item(item)
        self.fs.delete_item(item, appconfig.common.users_delete_to_recycle_dir)

        pluggy_pm.hook.collection_files_deleted(files=[item.processed])

        # # and remove from client db collection so gallery is up to date.
        # event is even sent if not show_in_gallery, client needs to sort things out
        sse_service.dispatch_event(SseEventDbRemove(mediaitem=MediaitemPublic.model_validate(item)))

    def clear_all(self):
        deleted_count = self.db.clear_all()
        logger.info(f"deleted {deleted_count} items from the database")

        self.fs.clear_all()
        logger.info("media files cleared")

        self.cache.clear_all()
        logger.info("cache cleared")

    def count(self) -> int:
        return self.db.count()

    def list_items(self, offset: int = 0, limit: int = 500) -> list[Mediaitem]:
        return self.db.list_items(offset, limit)

    def get_item(self, item_id: UUID, check_representing_files_raise: bool = True) -> Mediaitem:
        assert isinstance(item_id, UUID), "item_id must be UUID type!"

        item = self.db.get_item(item_id)

        if check_representing_files_raise:
            # on delete the check is usually skipped, because we want to proceed deleting then and need item returned...
            self.fs.check_representing_files_raise(item)

        return item

    def get_item_latest(self) -> Mediaitem:
        try:
            with Session(engine) as session:
                return session.scalars(select(Mediaitem).order_by(Mediaitem.rowid.desc()).limit(1)).one()
        except NoResultFound as exc:
            raise FileNotFoundError("could not find an item") from exc

    def get_items_relto_job(self, job_identifier: UUID) -> list[Mediaitem]:
        with Session(engine) as session:
            galleryitems = list(
                session.scalars(select(Mediaitem).order_by(Mediaitem.rowid.desc()).where(Mediaitem.job_identifier == job_identifier)).all()
            )

            return galleryitems
