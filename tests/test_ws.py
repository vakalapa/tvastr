"""Tests for the FastAPI WebSocket endpoints."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tvastr.server.events import EventBus, event_bus
from tvastr.server.schema import WSEventType, WSMessage
from tvastr.server.ws import configure, router
from tvastr.state.db import Iteration, StateDB


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app that mounts the ws router."""
    app = FastAPI()
    app.include_router(router)
    return app


def _make_msg(
    run_id: str = "run-1",
    agent_id: str | None = None,
    event: WSEventType = WSEventType.iteration_end,
) -> WSMessage:
    return WSMessage(type=event, run_id=run_id, agent_id=agent_id, payload={"x": 1})


@pytest.fixture()
def tmp_db(tmp_path: Path) -> StateDB:
    """Create a temporary StateDB for testing."""
    return StateDB(tmp_path / "test.db")


@pytest.fixture(autouse=True)
def _fresh_event_bus():
    """Reset the global event bus between tests so subscribers don't leak."""
    from tvastr.server import events as events_mod

    original = events_mod.event_bus
    fresh = EventBus()
    events_mod.event_bus = fresh

    # Also patch the reference in the ws module
    from tvastr.server import ws as ws_mod

    ws_mod.event_bus = fresh
    yield fresh
    events_mod.event_bus = original
    ws_mod.event_bus = original


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_make_app())


# ------------------------------------------------------------------
# 1. Connect to /ws/{run_id}
# ------------------------------------------------------------------


def test_connect_to_run_channel(client: TestClient, _fresh_event_bus: EventBus):
    """Client can connect to /ws/{run_id} and the socket is open."""
    configure(None)  # no DB for replay
    bus = _fresh_event_bus

    with client.websocket_connect("/ws/run-1") as ws:
        # Publish an event so we can verify the connection works.
        bus.publish("run:run-1", _make_msg(run_id="run-1"))
        data = ws.receive_json()
        assert data["type"] == WSEventType.iteration_end.value
        assert data["run_id"] == "run-1"


# ------------------------------------------------------------------
# 2. Receive events after publish
# ------------------------------------------------------------------


def test_receive_events_after_publish(client: TestClient, _fresh_event_bus: EventBus):
    """Events published to the run channel are received by the WebSocket client."""
    configure(None)
    bus = _fresh_event_bus

    with client.websocket_connect("/ws/r2") as ws:
        for i in range(3):
            bus.publish("run:r2", _make_msg(run_id="r2"))

        for i in range(3):
            data = ws.receive_json()
            assert data["run_id"] == "r2"


# ------------------------------------------------------------------
# 3. Agent-specific channel
# ------------------------------------------------------------------


def test_agent_specific_channel(client: TestClient, _fresh_event_bus: EventBus):
    """Client connected to /ws/{run_id}/{agent_id} receives agent events."""
    configure(None)
    bus = _fresh_event_bus

    with client.websocket_connect("/ws/r3/agent-0") as ws:
        bus.publish(
            "agent:r3:agent-0",
            _make_msg(run_id="r3", agent_id="agent-0"),
        )
        data = ws.receive_json()
        assert data["agent_id"] == "agent-0"
        assert data["run_id"] == "r3"


# ------------------------------------------------------------------
# 4. Disconnect handling
# ------------------------------------------------------------------


def test_disconnect_cleans_up(client: TestClient, _fresh_event_bus: EventBus):
    """After disconnect, the subscriber is removed from the event bus."""
    configure(None)
    bus = _fresh_event_bus

    with client.websocket_connect("/ws/r4") as ws:
        bus.publish("run:r4", _make_msg(run_id="r4"))
        ws.receive_json()

    # After context manager exits (disconnect), publishing should not error.
    bus.publish("run:r4", _make_msg(run_id="r4"))
    # No subscribers should remain for this channel.
    assert "run:r4" not in bus._subscribers or len(bus._subscribers["run:r4"]) == 0


# ------------------------------------------------------------------
# 5. Replay of recent iterations on connect
# ------------------------------------------------------------------


def test_replay_on_connect(client: TestClient, tmp_db: StateDB, _fresh_event_bus: EventBus):
    """On connect, recent iterations from StateDB are replayed."""
    configure(tmp_db)
    bus = _fresh_event_bus

    # Seed the DB with some iterations.
    for i in range(1, 4):
        tmp_db.log_iteration(
            Iteration(
                agent_id="agent-0",
                sub_objective_id=None,
                iteration_num=i,
                hypothesis=f"hypothesis-{i}",
                outcome="advanced",
                lesson=f"lesson-{i}",
            )
        )

    with client.websocket_connect("/ws/r5") as ws:
        # We should receive 3 replay messages (oldest first).
        replayed = []
        for _ in range(3):
            data = ws.receive_json()
            replayed.append(data)

        assert len(replayed) == 3
        # Oldest first
        assert replayed[0]["payload"]["iteration_num"] == 1
        assert replayed[1]["payload"]["iteration_num"] == 2
        assert replayed[2]["payload"]["iteration_num"] == 3

    # Clean up
    configure(None)


# ------------------------------------------------------------------
# 6. Agent replay only shows that agent's iterations
# ------------------------------------------------------------------


def test_agent_replay_filtered(
    client: TestClient, tmp_db: StateDB, _fresh_event_bus: EventBus
):
    """Replay on agent channel only includes that agent's iterations."""
    configure(tmp_db)

    # Seed iterations for two agents.
    for i in range(1, 4):
        tmp_db.log_iteration(
            Iteration(
                agent_id="agent-0",
                sub_objective_id=None,
                iteration_num=i,
                hypothesis=f"a0-hyp-{i}",
                outcome="advanced",
                lesson="ok",
            )
        )
    for i in range(1, 3):
        tmp_db.log_iteration(
            Iteration(
                agent_id="agent-1",
                sub_objective_id=None,
                iteration_num=i,
                hypothesis=f"a1-hyp-{i}",
                outcome="advanced",
                lesson="ok",
            )
        )

    with client.websocket_connect("/ws/r6/agent-1") as ws:
        replayed = []
        for _ in range(2):
            data = ws.receive_json()
            replayed.append(data)

        assert len(replayed) == 2
        assert all(d["agent_id"] == "agent-1" for d in replayed)

    configure(None)


# ------------------------------------------------------------------
# 7. Fan-out: agent event received on run channel via WebSocket
# ------------------------------------------------------------------


def test_fan_out_via_websocket(client: TestClient, _fresh_event_bus: EventBus):
    """An event published to agent:X:Y is received on /ws/X (run channel)."""
    configure(None)
    bus = _fresh_event_bus

    with client.websocket_connect("/ws/r7") as ws:
        bus.publish(
            "agent:r7:a1",
            _make_msg(run_id="r7", agent_id="a1"),
        )
        data = ws.receive_json()
        assert data["run_id"] == "r7"
        assert data["agent_id"] == "a1"


# ------------------------------------------------------------------
# 8. Multiple event types
# ------------------------------------------------------------------


def test_multiple_event_types(client: TestClient, _fresh_event_bus: EventBus):
    """Different event types are correctly serialized."""
    configure(None)
    bus = _fresh_event_bus

    with client.websocket_connect("/ws/r8") as ws:
        bus.publish(
            "run:r8",
            _make_msg(run_id="r8", event=WSEventType.run_status_change),
        )
        bus.publish(
            "run:r8",
            _make_msg(run_id="r8", event=WSEventType.agent_status_change),
        )

        d1 = ws.receive_json()
        d2 = ws.receive_json()
        assert d1["type"] == "run_status_change"
        assert d2["type"] == "agent_status_change"
