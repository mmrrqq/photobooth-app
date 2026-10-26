import logging
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from ...database.database import engine
from ...database.models import Mediaitem

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        pass

    def add_item(self, item: Mediaitem):
        # add to db and notify
        with Session(engine) as session:
            session.add(item)
            session.commit()
            session.refresh(item)

    def update_item(self, item: Mediaitem):
        with Session(engine) as session:
            session.add(item)
            session.commit()
            session.refresh(item)

    def delete_item(self, item: Mediaitem):
        with Session(engine) as session:
            session.delete(item)
            session.commit()

    def clear_all(self) -> int:
        with Session(engine) as session:
            statement = delete(Mediaitem)
            result = cast(CursorResult, session.execute(statement))
            session.commit()

            return result.rowcount

    def count(self) -> int:
        with Session(engine) as session:
            statement = select(func.count(Mediaitem.id))
            return session.scalars(statement).one()

    def list_items(self, offset: int = 0, limit: int = 500) -> list[Mediaitem]:
        with Session(engine) as session:
            galleryitems = list(
                session.scalars(select(Mediaitem).where(Mediaitem.show_in_gallery).order_by(Mediaitem.rowid.desc()).offset(offset).limit(limit)).all()
            )

            return galleryitems

    def get_item(self, item_id: UUID) -> Mediaitem:
        try:
            with Session(engine) as session:
                results = session.scalars(select(Mediaitem).where(Mediaitem.id == item_id))
                item = results.one()

                return item
        except NoResultFound as exc:
            raise FileNotFoundError(f"could not find {item_id} in database") from exc
