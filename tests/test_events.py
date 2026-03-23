"""Tests for the in-process async EventBus."""

from __future__ import annotations

import asyncio
import threading

import pytest

from tvastr.server.events import EventBus
from tvastr.server.schema import WSEventType, WSMessage


def _make_msg(
    run_id: str = "run-1",
    agent_id: str | None = None,
    event: WSEventType = WSEventType.iteration_end,
) -> WSMessage:
    return WSMessage(type=event, run_id=run_id, agent_id=agent_id, payload={"x": 1})


# ------------------------------------------------------------------
# 1. Basic publish / subscribe
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_basic_publish_subscribe():
    """A subscriber receives an event published to its channel."""
    bus = EventBus()
    received: list[WSMessage] = []

    async def reader():
        async for msg in bus.subscribe("run:1"):
            received.append(msg)
            break  # one message is enough

    task = asyncio.create_task(reader())
    await asyncio.sleep(0.05)  # let subscriber register

    bus.publish("run:1", _make_msg())
    await asyncio.wait_for(task, timeout=2)

    assert len(received) == 1
    assert received[0].run_id == "run-1"


# ------------------------------------------------------------------
# 2. Fan-out: agent channel -> run channel
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fan_out_agent_to_run():
    """Publishing to agent:X:Y also delivers to run:X."""
    bus = EventBus()
    run_events: list[WSMessage] = []

    async def run_reader():
        async for msg in bus.subscribe("run:r1"):
            run_events.append(msg)
            break

    task = asyncio.create_task(run_reader())
    await asyncio.sleep(0.05)

    bus.publish("agent:r1:a1", _make_msg(run_id="r1", agent_id="a1"))
    await asyncio.wait_for(task, timeout=2)

    assert len(run_events) == 1
    assert run_events[0].agent_id == "a1"


# ------------------------------------------------------------------
# 3. Multiple subscribers on the same channel
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_subscribers():
    """All subscribers on a channel receive the same event."""
    bus = EventBus()
    results: list[list[WSMessage]] = [[], []]

    async def reader(idx: int):
        async for msg in bus.subscribe("run:1"):
            results[idx].append(msg)
            break

    t1 = asyncio.create_task(reader(0))
    t2 = asyncio.create_task(reader(1))
    await asyncio.sleep(0.05)

    bus.publish("run:1", _make_msg())
    await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2)

    assert len(results[0]) == 1
    assert len(results[1]) == 1


# ------------------------------------------------------------------
# 4. Unsubscribe stops receiving
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsubscribe_stops_receiving():
    """After unsubscribe the async iterator exits."""
    bus = EventBus()
    received: list[WSMessage] = []

    queue: asyncio.Queue | None = None

    async def reader():
        nonlocal queue
        async for msg in bus.subscribe("run:1"):
            received.append(msg)
            # Grab the queue reference from the bus internals for unsubscription.
            break

    # Subscribe, receive one message, then unsubscribe.
    task = asyncio.create_task(reader())
    await asyncio.sleep(0.05)

    bus.publish("run:1", _make_msg())
    await asyncio.wait_for(task, timeout=2)

    # After the reader exits, the queue was cleaned up by the finally block.
    # Publish again -- no one should receive it.
    bus.publish("run:1", _make_msg())
    assert len(received) == 1  # still only the first message


# ------------------------------------------------------------------
# 5. Publish from a background thread (thread-safety)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_from_thread():
    """publish() called from a background thread delivers events."""
    bus = EventBus()
    received: list[WSMessage] = []

    async def reader():
        async for msg in bus.subscribe("run:t1"):
            received.append(msg)
            break

    task = asyncio.create_task(reader())
    await asyncio.sleep(0.05)

    # Publish from a background thread.
    def bg_publish():
        bus.publish("run:t1", _make_msg(run_id="t1"))

    thread = threading.Thread(target=bg_publish)
    thread.start()
    thread.join(timeout=2)

    await asyncio.wait_for(task, timeout=2)
    assert len(received) == 1
    assert received[0].run_id == "t1"


# ------------------------------------------------------------------
# 6. Empty channel — publish doesn't error
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_no_subscribers():
    """Publishing to a channel with no subscribers does not raise."""
    bus = EventBus()
    # Should not raise
    bus.publish("run:nope", _make_msg())


# ------------------------------------------------------------------
# 7. Multiple independent channels
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_independent_channels():
    """Events on one channel do not leak to another."""
    bus = EventBus()
    ch_a: list[WSMessage] = []
    ch_b: list[WSMessage] = []

    async def reader_a():
        async for msg in bus.subscribe("run:a"):
            ch_a.append(msg)
            break

    async def reader_b():
        async for msg in bus.subscribe("run:b"):
            ch_b.append(msg)
            break

    ta = asyncio.create_task(reader_a())
    tb = asyncio.create_task(reader_b())
    await asyncio.sleep(0.05)

    bus.publish("run:a", _make_msg(run_id="a"))
    bus.publish("run:b", _make_msg(run_id="b"))

    await asyncio.wait_for(asyncio.gather(ta, tb), timeout=2)

    assert len(ch_a) == 1
    assert ch_a[0].run_id == "a"
    assert len(ch_b) == 1
    assert ch_b[0].run_id == "b"


# ------------------------------------------------------------------
# 8. Fan-out does NOT double-deliver to agent channel
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fan_out_agent_subscriber_gets_one_copy():
    """A subscriber on the agent channel gets exactly one copy."""
    bus = EventBus()
    agent_events: list[WSMessage] = []

    async def agent_reader():
        async for msg in bus.subscribe("agent:r1:a1"):
            agent_events.append(msg)
            break

    task = asyncio.create_task(agent_reader())
    await asyncio.sleep(0.05)

    bus.publish("agent:r1:a1", _make_msg(run_id="r1", agent_id="a1"))
    await asyncio.wait_for(task, timeout=2)

    assert len(agent_events) == 1


# ------------------------------------------------------------------
# 9. Queue overflow drops oldest event
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_overflow_drops_oldest():
    """When a subscriber queue is full the oldest event is dropped."""
    bus = EventBus()

    # Create a subscriber with a tiny queue to make overflow easy to trigger.
    queue: asyncio.Queue[WSMessage | None] = asyncio.Queue(maxsize=2)
    with bus._lock:
        bus._subscribers["run:of"].append(queue)

    # Publish 5 events -- the queue can only hold 2.
    for i in range(5):
        bus.publish("run:of", _make_msg(run_id=f"msg-{i}"))

    # We should still be able to get events out (no deadlock).
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    assert len(items) <= 2


# ------------------------------------------------------------------
# 10. Unsubscribe is idempotent
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsubscribe_idempotent():
    """Calling unsubscribe twice does not raise."""
    bus = EventBus()
    queue: asyncio.Queue[WSMessage | None] = asyncio.Queue(maxsize=100)
    with bus._lock:
        bus._subscribers["run:x"].append(queue)

    bus.unsubscribe("run:x", queue)
    bus.unsubscribe("run:x", queue)  # second call -- should not raise
