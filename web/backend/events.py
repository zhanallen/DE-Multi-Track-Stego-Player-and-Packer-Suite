"""Server-Sent Events plumbing.

The decoder runs in a plain thread while SSE responses live on the asyncio
event loop. ``EventBroadcaster.publish`` may be called from any thread; it hands
each event to subscriber queues through ``loop.call_soon_threadsafe`` so the
asyncio side never touches shared state from a foreign thread.
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass

HEARTBEAT_COMMENT = ": heartbeat\n\n"


@dataclass(frozen=True)
class ServerEvent:
    name: str
    data: dict


def format_sse(event: ServerEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False)
    return f"event: {event.name}\ndata: {payload}\n\n"


class Subscription:
    """One SSE client's inbox, bound to the event loop that created it."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._queue: asyncio.Queue[ServerEvent] = asyncio.Queue()

    def deliver(self, event: ServerEvent) -> None:
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            # Loop already closed (server shutting down); the client is gone anyway.
            pass

    async def wait_for_event(self, timeout_sec: float) -> ServerEvent | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            return None


class EventBroadcaster:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscriptions: set[Subscription] = set()

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> Subscription:
        subscription = Subscription(loop)
        with self._lock:
            self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)

    def publish(self, event: ServerEvent) -> None:
        with self._lock:
            targets = list(self._subscriptions)
        for subscription in targets:
            subscription.deliver(event)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)


async def stream_sse(
    first_event: ServerEvent,
    subscription: Subscription,
    heartbeat_sec: float,
) -> AsyncIterator[str]:
    """Yield the snapshot first, then live events, with periodic heartbeats.

    The stream stays open after terminal events so EventSource does not keep
    reconnecting; Starlette cancels this generator when the client disconnects.
    """
    yield format_sse(first_event)
    while True:
        event = await subscription.wait_for_event(heartbeat_sec)
        yield HEARTBEAT_COMMENT if event is None else format_sse(event)
