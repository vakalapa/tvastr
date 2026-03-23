"""In-process async event bus for streaming forge events to WebSocket clients."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from typing import AsyncIterator

from tvastr.server.schema import WSMessage

logger = logging.getLogger(__name__)


class EventBus:
    """Pub/sub event bus for streaming forge events to WebSocket clients.

    Channels follow the pattern:
        - ``run:{run_id}`` -- all events for a forge run
        - ``agent:{run_id}:{agent_id}`` -- events for a single agent

    Publishing to an agent channel automatically fans out to the
    corresponding run channel.

    Thread-safe: ``publish`` may be called from synchronous background
    threads (e.g. the forge agent iteration loop).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[WSMessage | None]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(self, channel: str, event: WSMessage) -> None:
        """Publish an event to *channel*. Non-blocking and thread-safe.

        If the channel looks like ``agent:{run_id}:{agent_id}`` the event
        is also delivered to the ``run:{run_id}`` channel (fan-out).
        """
        channels = [channel]

        # Fan-out: agent channel -> run channel
        parts = channel.split(":")
        if parts[0] == "agent" and len(parts) >= 3:
            run_channel = f"run:{parts[1]}"
            channels.append(run_channel)

        with self._lock:
            for ch in channels:
                for queue in self._subscribers.get(ch, []):
                    self._enqueue(queue, event)

    async def subscribe(self, channel: str) -> AsyncIterator[WSMessage]:
        """Subscribe to *channel*. Yields events as they arrive.

        The returned async iterator blocks until an event is available.
        Call :meth:`unsubscribe` (or cancel the task) to stop iteration.
        """
        queue: asyncio.Queue[WSMessage | None] = asyncio.Queue(maxsize=1000)

        with self._lock:
            self._subscribers[channel].append(queue)
            # Capture the running loop so publish() from threads can use it.
            if self._loop is None:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass

        try:
            while True:
                item = await queue.get()
                if item is None:
                    # Sentinel: subscription ended.
                    break
                yield item
        finally:
            self.unsubscribe(channel, queue)

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber's queue from *channel*."""
        with self._lock:
            subs = self._subscribers.get(channel, [])
            try:
                subs.remove(queue)
            except ValueError:
                pass
            if not subs and channel in self._subscribers:
                del self._subscribers[channel]

        # Push a sentinel so the subscriber's async iterator exits cleanly.
        self._enqueue(queue, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enqueue(self, queue: asyncio.Queue, item: WSMessage | None) -> None:
        """Put *item* into *queue*, handling cross-thread delivery."""
        try:
            loop = self._loop
            if loop is not None and loop.is_running() and loop != _current_loop():
                # Called from a background thread -- schedule onto the event loop.
                loop.call_soon_threadsafe(self._put_nowait, queue, item)
            else:
                self._put_nowait(queue, item)
        except Exception:
            logger.debug("EventBus: failed to enqueue event", exc_info=True)

    @staticmethod
    def _put_nowait(queue: asyncio.Queue, item: WSMessage | None) -> None:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            # Drop oldest event to prevent unbounded memory growth.
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                pass


def _current_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


# Global singleton --------------------------------------------------------
event_bus = EventBus()
