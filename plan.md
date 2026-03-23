# P3 Web UI — Execution Plan (4 Sub-Agents)

## Strategy

Define the **API contract first** (shared types + OpenAPI-style endpoint signatures), then let 4 agents work independently against that contract. Server agents read from existing `StateDB`; frontend agents code against the typed API contract.

---

## Pre-work (main agent, before spawning sub-agents)

Create the shared contract file `tvastr/server/schema.py` with Pydantic models that both server and frontend agents reference. This is the **interface boundary**.

```python
# tvastr/server/schema.py — shared API types
# Pydantic models for: RunConfig, RunStatus, AgentStatus, SubObjectiveOut,
# IterationOut, MergeResultOut, ValidationResultOut, ControlAction
# Plus WebSocket message envelope: WSMessage(type, payload, timestamp)
```

Also create skeleton directories:
```
tvastr/server/__init__.py
tvastr/server/schema.py      # shared contract
tvastr/server/app.py          # placeholder
tvastr/server/ws.py           # placeholder
tvastr/server/routes/         # placeholder
ui/                           # placeholder
```

Install deps: add `fastapi`, `uvicorn[standard]`, `websockets` to pyproject.toml.

---

## Sub-Agent 1: REST API Server

**Scope:** `tvastr/server/app.py` + `tvastr/server/routes/`

**Creates:**
- `tvastr/server/app.py` — FastAPI app factory, CORS, lifespan, mount routes
- `tvastr/server/routes/__init__.py`
- `tvastr/server/routes/runs.py` — Start/stop/list forge runs
  - `POST /api/runs` — start a forge run (returns run_id, launches in background)
  - `GET /api/runs` — list active/completed runs
  - `GET /api/runs/{run_id}` — run status + progress
  - `POST /api/runs/{run_id}/cancel` — cancel a run
- `tvastr/server/routes/agents.py` — Agent status + iterations
  - `GET /api/runs/{run_id}/agents` — list agents for a run
  - `GET /api/runs/{run_id}/agents/{agent_id}` — agent detail
  - `GET /api/runs/{run_id}/agents/{agent_id}/iterations` — iteration history
- `tvastr/server/routes/objectives.py` — Sub-objectives
  - `GET /api/runs/{run_id}/objectives` — list sub-objectives + status
- `tvastr/server/routes/controls.py` — Runtime controls
  - `POST /api/runs/{run_id}/pause`
  - `POST /api/runs/{run_id}/resume`
  - `POST /api/runs/{run_id}/agents/{agent_id}/kill`

**Reads from:** `StateDB` (existing), schema.py (shared contract)
**Key detail:** Runs launch `ForgeMaster.run()` in a background thread/task. A `RunManager` dict tracks active runs by run_id with their StateDB path + status.

---

## Sub-Agent 2: WebSocket Server + Event Bus

**Scope:** `tvastr/server/ws.py` + `tvastr/server/events.py`

**Creates:**
- `tvastr/server/events.py` — In-process event bus
  - `EventBus` class with `publish(channel, event)` and `subscribe(channel) -> AsyncIterator`
  - Channels: `run:{run_id}`, `agent:{run_id}:{agent_id}`
  - Event types: `iteration_start`, `iteration_end`, `agent_output`, `validation_result`, `run_complete`, `agent_error`
- `tvastr/server/ws.py` — WebSocket endpoint
  - `GET /ws/{run_id}` — stream all events for a run
  - `GET /ws/{run_id}/{agent_id}` — stream events for one agent
  - Sends JSON messages matching `WSMessage` schema
  - Handles client disconnect gracefully
- Hooks into existing code: patches `ForgeAgent._run_iteration` and `ForgeMaster.run` to emit events (via a callback/hook pattern, not by modifying those files directly — use an adapter/wrapper)

**Reads from:** schema.py (WSMessage type), StateDB for replay of past events on connect

---

## Sub-Agent 3: React Frontend — Shell + Dashboard + Agent Views

**Scope:** `ui/` directory — app shell, dashboard, agent stream, iteration timeline

**Creates:**
```
ui/
├── package.json              # react 18, typescript, vite, tailwind, tanstack-query
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx               # Router: /, /runs/:id, /runs/:id/agents/:agentId
│   ├── api/
│   │   ├── client.ts         # fetch wrapper, base URL config
│   │   ├── types.ts          # TypeScript types mirroring schema.py
│   │   └── queries.ts        # TanStack Query hooks (useRuns, useAgents, useIterations, etc.)
│   ├── hooks/
│   │   └── useWebSocket.ts   # Generic WS hook, auto-reconnect, JSON parse
│   ├── components/
│   │   ├── Layout.tsx         # Sidebar + header shell
│   │   ├── Dashboard.tsx      # Active runs list, overall progress bars
│   │   ├── RunView.tsx        # Single run: agents grid, sub-objectives, merge status
│   │   ├── AgentStream.tsx    # Live terminal-style output for one agent (WS)
│   │   └── Timeline.tsx       # Iteration timeline, color-coded pass/fail/revert
│   └── index.css              # Tailwind base
```

**Contract dependency:** Reads `api/types.ts` which mirrors `schema.py`. Does NOT call real API — uses TanStack Query hooks that hit `/api/*` and `/ws/*`.

---

## Sub-Agent 4: React Frontend — Patch Viewer + Controls + Test Results

**Scope:** Additional components + integration into the app shell from Agent 3

**Creates:**
```
ui/src/
├── components/
│   ├── PatchViewer.tsx        # Side-by-side diff viewer (uses react-diff-viewer or custom)
│   ├── TestResults.tsx        # Expandable test output, filterable by status
│   ├── Journal.tsx            # Searchable table of all iterations with lessons
│   └── Controls.tsx           # Pause/resume/kill buttons, objective editor
├── api/
│   └── mutations.ts           # TanStack mutations (pauseRun, resumeRun, killAgent, cancelRun)
```

**Key detail:** These components are imported by `RunView.tsx` (from Agent 3) via lazy loading. Agent 4 creates the components as standalone files. Agent 3 leaves `{/* PatchViewer, Controls, TestResults, Journal loaded here */}` placeholder imports that Agent 4's files fulfill.

---

## Dependency Graph

```
Pre-work (schema.py + skeleton)
       │
       ├──────────────────┬──────────────────┐
       ▼                  ▼                  ▼
  Agent 1 (REST)    Agent 2 (WS)     Agent 3 (FE shell)
                                           │
                                           ▼
                                     Agent 4 (FE extras)
```

- Agents 1, 2, 3 are **fully parallel** (no file overlap)
- Agent 4 depends on Agent 3 (needs the app shell + router to exist), but can start in parallel if it only creates standalone component files

---

## Integration (main agent, after all sub-agents)

1. Wire Agent 4's components into Agent 3's router/views (add imports)
2. Add `tvastr serve` CLI command to `cli.py` that launches uvicorn
3. Update `pyproject.toml` with all new deps
4. Smoke test: `pytest tests/` still passes (no regressions)
5. Commit + push

---

## Files touched per agent (no overlap)

| Agent | Files |
|-------|-------|
| Pre-work | `tvastr/server/__init__.py`, `tvastr/server/schema.py`, `pyproject.toml` |
| Agent 1 | `tvastr/server/app.py`, `tvastr/server/routes/*.py` |
| Agent 2 | `tvastr/server/ws.py`, `tvastr/server/events.py` |
| Agent 3 | `ui/*` (shell, dashboard, agent views, timeline, types, queries, hooks) |
| Agent 4 | `ui/src/components/PatchViewer.tsx`, `TestResults.tsx`, `Journal.tsx`, `Controls.tsx`, `ui/src/api/mutations.ts` |
| Integration | `tvastr/cli.py`, `ui/src/App.tsx` (wire imports), final test |
