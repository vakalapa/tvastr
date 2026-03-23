"""FastAPI WebSocket endpoints for streaming forge events."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tvastr.server.events import event_bus
from tvastr.server.schema import WSEventType, WSMessage
from tvastr.state.db import StateDB

logger = logging.getLogger(__name__)

router = APIRouter()

# The StateDB instance is set at application startup via ``configure``.
_state_db: Optional[StateDB] = None


def configure(db: StateDB) -> None:
    """Set the StateDB instance used for replaying recent iterations."""
    global _state_db
    _state_db = db


def _get_db() -> Optional[StateDB]:
    return _state_db


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _iteration_to_ws_message(row: dict, run_id: str) -> WSMessage:
    """Convert a DB iteration row into a WSMessage for replay."""
    return WSMessage(
        type=WSEventType.iteration_end,
        run_id=run_id,
        agent_id=row.get("agent_id"),
        payload={
            "iteration_num": row.get("iteration_num"),
            "hypothesis": row.get("hypothesis", ""),
            "files_changed": row.get("files_changed", "[]"),
            "outcome": row.get("outcome", ""),
            "lesson": row.get("lesson", ""),
            "patch_sha": row.get("patch_sha", ""),
        },
        timestamp=row.get("created_at", ""),
    )


async def _send_replay(ws: WebSocket, run_id: str, agent_id: str | None = None) -> None:
    """Send recent iterations from StateDB as replay on connect."""
    db = _get_db()
    if db is None:
        return

    iterations = db.get_iterations(agent_id=agent_id, limit=20)
    # Sort by iteration_num ascending so we send oldest first.
    iterations.sort(key=lambda r: (r.get("iteration_num", 0), r.get("id", 0)))
    for row in iterations:
        msg = _iteration_to_ws_message(row, run_id)
        await ws.send_text(json.dumps(msg.model_dump(mode="json")))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.websocket("/ws/{run_id}")
async def ws_run(ws: WebSocket, run_id: str) -> None:
    """Stream all events for a forge run."""
    await ws.accept()

    try:
        # Replay recent history.
        await _send_replay(ws, run_id)

        channel = f"run:{run_id}"
        async for event in event_bus.subscribe(channel):
            await ws.send_text(json.dumps(event.model_dump(mode="json")))
    except WebSocketDisconnect:
        logger.debug("Client disconnected from /ws/%s", run_id)
    except Exception:
        logger.debug("WebSocket error on /ws/%s", run_id, exc_info=True)


@router.websocket("/ws/{run_id}/{agent_id}")
async def ws_agent(ws: WebSocket, run_id: str, agent_id: str) -> None:
    """Stream events for a single agent within a forge run."""
    await ws.accept()

    try:
        # Replay recent history for this agent.
        await _send_replay(ws, run_id, agent_id=agent_id)

        channel = f"agent:{run_id}:{agent_id}"
        async for event in event_bus.subscribe(channel):
            await ws.send_text(json.dumps(event.model_dump(mode="json")))
    except WebSocketDisconnect:
        logger.debug("Client disconnected from /ws/%s/%s", run_id, agent_id)
    except Exception:
        logger.debug("WebSocket error on /ws/%s/%s", run_id, agent_id, exc_info=True)
