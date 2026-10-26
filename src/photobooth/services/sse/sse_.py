import asyncio
import json
import logging
import os
import time
import uuid
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Request
from pydantic import BaseModel
from sse_starlette.event import ServerSentEvent

from photobooth.services.processor.base import UiJobModel

from ...database.schemas import MediaitemPublic, ShareLimitsPublic, UsageStatsPublic
from ...models.genericstats import GenericStats

logger = logging.getLogger(__name__)


class SseEventBase(BaseModel):
    """basic class for sse events"""

    @property
    @abstractmethod
    def event(self) -> str:
        pass

    @property
    @abstractmethod
    def data(self) -> str:
        pass


class SseEventTranslateableFrontendNotification(SseEventBase):
    """some visible message in frontend"""

    message_key: str = ""
    context_data: dict[str, str] = field(default_factory=dict)
    color: str | None = None  # could a color or "positive", "negative", "warning", "info" or None, the UI default
    icon: str | None = None  # could a quasar icon or None, the UI default
    spinner: bool | None = None  # could be True or False, None same as False

    @property
    def event(self) -> str:
        return "TranslateableFrontendNotification"

    @property
    def data(self) -> str:
        return self.model_dump_json()


class SseEventProcessStateinfo(SseEventBase):
    """_summary_"""

    source: str | None
    target: str | None
    jobmodel: UiJobModel | None

    @property
    def event(self) -> str:
        return "ProcessStateinfo"

    @property
    def data(self) -> str:
        # either have it all or nothing
        if self.jobmodel and self.source and self.target:
            return self.model_dump_json()
        else:
            return json.dumps({})


class SseEventDbInsert(SseEventBase):
    mediaitem: MediaitemPublic

    @property
    def event(self) -> str:
        return "DbInsert"

    @property
    def data(self) -> str:
        return self.mediaitem.model_dump_json()


class SseEventDbUpdate(SseEventBase):
    mediaitem: MediaitemPublic

    @property
    def event(self) -> str:
        return "DbUpdate"

    @property
    def data(self) -> str:
        return self.mediaitem.model_dump_json()


class SseEventDbRemove(SseEventBase):
    mediaitem: MediaitemPublic

    @property
    def event(self) -> str:
        return "DbRemove"

    @property
    def data(self) -> str:
        return self.mediaitem.model_dump_json()


class SseEventLogRecord(SseEventBase):
    """basic class for sse events"""

    time: str
    level: str
    message: str
    name: str
    funcName: str
    lineno: str
    # display_notification: bool

    @property
    def event(self) -> str:
        return "LogRecord"

    @property
    def data(self) -> str:
        return self.model_dump_json()


class SseEventOnetimeInformationRecord(SseEventBase):
    """basic class for sse events"""

    version: str
    platform_system: str
    platform_release: str
    platform_machine: str
    platform_python_version: str
    platform_node: str
    platform_cpu_count: int | None
    model: str
    data_directory: Path
    python_executable: str
    disk: dict[str, int | float]

    @property
    def event(self) -> str:
        return "OnetimeInformationRecord"

    @property
    def data(self) -> str:
        return self.model_dump_json()


class SseEventIntervalInformationRecord(SseEventBase):
    """basic class for sse events"""

    cpu_percent: float
    memory: dict[str, int | float]
    cma: dict[str, int | None] | dict[str, None]
    backends: dict[str, dict[str, Any]]
    stats_counter: list[UsageStatsPublic]
    limits_counter: list[ShareLimitsPublic]
    battery_percent: int | None
    temperatures: dict[str, Any]
    mediacollection: dict[str, Any]
    plugins: list[GenericStats]
    pi_throttled_flags: dict[str, bool]

    @property
    def event(self) -> str:
        return "IntervalInformationRecord"

    @property
    def data(self) -> str:
        return self.model_dump_json()


@dataclass
class Client:
    """Class each individual client connected"""

    request: Request
    queue: asyncio.Queue[ServerSentEvent]


class SseService:
    def __init__(self):
        # keep track of client connections with each individual request and queue.
        self._clients: list[Client] = []

        # on app end a shutdown is requested to stop yielding and so disconnet live sse connections.
        # without stop yielding, uvcorn would wait infinite until all clients close the connection, which they do not do
        self._shutdown: bool = False

    def request_shutdown(self):
        # shutdown request is one way - the app will not recover from this but needs a restart to resume
        logger.debug("sse service shutdown requested to stop yielding messages")
        self._shutdown = True

    def setup_client(self, client: Client):
        self._clients.append(client)
        logger.debug(f"SSE clients connected: {[_client.request.client for _client in self._clients]}")
        # print(f"client.queue {[client.queue for client in self._clients]}")
        # print(f"qsize {[client.queue.qsize() for client in self._clients]}")

    def remove_client(self, client: Client):
        # iterate over client list and remove.
        for index, _client in enumerate(self._clients):
            if _client.request is client.request:
                removed_client = self._clients.pop(index)
                logger.debug(f"SSE subscription removed for {removed_client.request.client}")
                break

        logger.debug(f"SSE clients connected: {[_client.request.client for _client in self._clients]}")

    def dispatch_event(self, sse_event_data: SseEventBase):
        for client in self._clients:
            try:
                client.queue.put_nowait(
                    ServerSentEvent(
                        id=str(uuid.uuid4()),
                        event=sse_event_data.event,
                        data=sse_event_data.data,
                        retry=10000,
                    )
                )

            except asyncio.QueueFull:
                # fail in silence if queue is full - though is critical for init sse messages.
                # on the other side, queue better not infinite if disconnect is not working proper and queue remains getting larger
                pass

    async def event_iterator(self, client: Client, timeout: float = 0.0):
        if "PYTEST_CURRENT_TEST" in os.environ:
            # FIXME: workaround for testing until testing with mocks/patching works well...
            timeout = 3.5
            logger.info(f"event_iterator {timeout=} set. positive values used for testing only")

        try:
            starting_time = time.time()
            while not timeout or (time.time() - starting_time < timeout):
                if await client.request.is_disconnected():
                    self.remove_client(client)
                    logger.info(f"client request disconnect, client {client.request.client}")
                    break

                if self._shutdown:
                    logger.info("Shutdown requested, stopping event_iterator")
                    break

                try:
                    yield await asyncio.wait_for(client.queue.get(), timeout=0.5)
                except asyncio.exceptions.TimeoutError:
                    # continue on timeouterror ignore silently. used to abort while loop for testing
                    continue

        except asyncio.CancelledError as exc:
            self.remove_client(client)
            logger.info(f"Disconnected from client {client.request.client}")

            # https://stackoverflow.com/a/53724990
            raise exc

        finally:
            # Cleanup always happens
            logger.info(f"Cleaning up stream {client.request.client}")
            self.remove_client(client)
