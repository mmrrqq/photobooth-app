import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, get_args

from sqlalchemy import UUID, Boolean, DateTime, Enum, ForeignKey, Integer, String, event
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

from .types import DimensionTypes, MediaitemTypes, PathType


class Base(DeclarativeBase):
    pass


class UsageStats(Base):
    __tablename__ = "usagestats"

    action: Mapped[str] = mapped_column(String, default=None, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShareLimits(Base):
    __tablename__ = "sharelimits"

    action: Mapped[str] = mapped_column(String, default=None, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Mediaitem(Base):
    __tablename__ = "mediaitems"

    rowid: Mapped[int] = mapped_column(Integer, system=True)  # used to get last item (https://stackoverflow.com/a/78857439)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)
    media_type: Mapped[MediaitemTypes] = mapped_column(Enum(*get_args(MediaitemTypes)))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # used for cache invalidation/browser cache busting

    job_identifier: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=None)

    # the original as captured from camera. Defaults to false because phase2 items (collage, animations) to not have a captured original
    captured_original: Mapped[Path | None] = mapped_column(PathType, default=None)
    # processed full-dimension, filter pipeline applied
    processed: Mapped[Path] = mapped_column(PathType)

    pipeline_config: Mapped[dict[str, Any]] = mapped_column(JSON)  # json config of pipeline
    show_in_gallery: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}> ({self.processed.name})"


@event.listens_for(Mediaitem, "before_update")
def increment_revision(mapper, connection, target):
    target.revision = (target.revision or 0) + 1


class Cacheditem(Base):
    __tablename__ = "cacheditems"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    # following are the unique combination to identify if a cached obj is avail or no
    mediaitem_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mediaitems.id"), index=True)
    dimension: Mapped[DimensionTypes] = mapped_column(Enum(*get_args(DimensionTypes)), index=True)
    processed: Mapped[bool] = mapped_column(Boolean, index=True)

    # revision is used to detect if the original mediaitem was updated (new filter applied, or something)
    # originally (before v9) we used updated_at/created_at but it has only 1s accuracy and can cause problems on fast systems
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    filepath: Mapped[Path] = mapped_column(PathType)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}> filepath: {self.filepath}, dimension: {self.dimension}"
