import logging
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.orm.attributes import flag_modified

from photobooth.database.models import Mediaitem
from photobooth.services.collection import MediacollectionService
from tests.tests.util import dummy_mediaitem

logger = logging.getLogger(name=None)


@pytest.fixture()
def cs():
    # setup
    cs = MediacollectionService()

    yield cs


def test_start_maintain(cs: MediacollectionService):
    with patch.object(cs, "on_start_maintain") as mock:
        cs.start()

        mock.assert_called()


def test_start_stop(cs: MediacollectionService):
    cs.start()
    cs.stop()
    cs.stop()


def test_maintain(cs: MediacollectionService):
    cs.on_start_maintain()


def test_add_item(cs: MediacollectionService):
    count_before = cs.count()

    cs.add_item(dummy_mediaitem())

    assert count_before + 1 == cs.count()


def test_add_item_filedoesntexist(cs: MediacollectionService):
    count_before = cs.count()

    with pytest.raises(FileNotFoundError):
        cs.add_item(
            Mediaitem(
                job_identifier=uuid4(),
                media_type="image",
                processed=Path("./src/tests/assets/input_nonexistant.jpg"),
                pipeline_config={},
                show_in_gallery=True,
            )
        )

    assert count_before == cs.count()


def test_update_item_increments_revision(cs: MediacollectionService):
    dummy_item = dummy_mediaitem()
    cs.add_item(dummy_item)
    revision_before_update = dummy_item.revision

    # "simulate" a change, so the item is updated actually in the db.
    flag_modified(dummy_item, "pipeline_config")

    cs.update_item(dummy_item)

    assert dummy_item.revision > revision_before_update


def test_update_item_nochange_not_increment_revision(cs: MediacollectionService):
    dummy_item = dummy_mediaitem()
    cs.add_item(dummy_item)
    revision_before_update = dummy_item.revision

    cs.update_item(dummy_item)

    assert dummy_item.revision == revision_before_update


def test_delete_item(cs: MediacollectionService):
    dummy_item = dummy_mediaitem()
    cs.add_item(dummy_item)
    count_before = cs.count()

    cs.delete_item(dummy_item)

    assert count_before - 1 == cs.count()
