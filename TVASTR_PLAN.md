# TVASTR

> *Named after the Vedic divine craftsman who forged the weapons of the gods.*

Autonomous craftsman that forges, deploys, and validates code changes against live infrastructure. Give it an objective, a repo, and a cluster — it iterates until the objective is met or it exhausts its budget.

---

## Core Philosophy: Orchestrate, Don't Build

Tvastr is a **pure orchestrator**. It does not embed knowledge about how to build, test, or deploy any specific project. Instead, it spawns intelligent agents that **discover** how the target repo works by reading its own documentation:

- `README.md`, `CONTRIBUTING.md`, `CLAUDE.md` — project setup, build commands, test instructions
- `Makefile`, `Dockerfile`, `docker-compose.yml`, `package.json`, `pyproject.toml` — build tooling
- `.github/workflows/`, `.gitlab-ci.yml` — CI pipelines as a source of truth
- Existing test scripts, linting configs, `.tvastr/objective.md`

**Why no built-in builder/deployer?** Every repo is different. A Go monorepo builds differently from a Python library, which builds differently from a Rust microservice. Encoding build/deploy logic in tvastr creates brittle abstractions that inevitably lag behind real-world repos. The LLM agent can read a README and figure it out — just like a human engineer joining a new team.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      TVASTR CLI                         │
│              tvastr run --objective obj.md               │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│                   FORGE MASTER                           │
│         (Orchestrator — Claude Agent SDK)                │
│                                                         │
│  • Reads objective.md                                   │
│  • Decomposes into parallel sub-objectives              │
│  • Spawns & coordinates forge agents                    │
│  • Merges successful patches                            │
│  • Resolves conflicts between agents                    │
└──────┬────────────┬────────────┬────────────────────────┘
       │            │            │
┌──────▼───┐  ┌────▼─────┐  ┌──▼──────────┐
│ Agent 1  │  │ Agent 2  │  │  Agent N    │
│          │  │          │  │             │
│ Discovers│  │ Discovers│  │ Discovers   │
│ repo docs│  │ repo docs│  │ repo docs   │
│ & builds │  │ & tests  │  │ & deploys   │
└──────┬───┘  └────┬─────┘  └──┬──────────┘
       │            │            │
┌──────▼────────────▼────────────▼────────────────────────┐
│                  SHARED STATE (SQLite)                    │
│  • Iteration journal   • Agent claims/locks              │
│  • Test results        • Patch history                   │
│  • Baselines           • Conflict log                    │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│              WEB UI (React + WebSocket)                   │
│  • Live agent streams   • Iteration timeline             │
│  • Test results grid    • Patch diff viewer              │
└─────────────────────────────────────────────────────────┘
```

---

## How Agents Discover a Repo

When an agent starts working on a repo, its **first action** is a discovery phase:

1. **Read repo documentation** — README.md, CONTRIBUTING.md, CLAUDE.md, any docs/ directory
2. **Inspect build tooling** — Makefile, Dockerfile, package.json, pyproject.toml, Cargo.toml, go.mod, etc.
3. **Inspect CI configuration** — .github/workflows/*.yml, .gitlab-ci.yml, Jenkinsfile
4. **Understand test conventions** — where tests live, how to run them, what frameworks are used
5. **Check for existing tvastr hints** — .tvastr/repo.yaml (optional, lightweight hints only)

The agent then uses `run_command` to build, test, and deploy — using whatever commands the repo's own docs specify. No abstractions. No adapters. Just an intelligent agent reading docs and running commands, exactly like a human would.

### .tvastr/repo.yaml (optional, minimal)

The repo config is now **optional** and **minimal** — just hints to save the agent time, not a required schema:

```yaml
# Optional hints for the agent. The agent can discover all of this
# from the repo's own docs, but hints speed up the first iteration.
hints:
  language: python
  test_command: "python -m pytest tests/ -v"
  build_command: "pip install -e ."
  docs:
    - README.md
    - CONTRIBUTING.md
```

If no repo.yaml exists, the agent reads the repo's own documentation and figures it out. This is the expected default path.

---

## Concrete Example: Native Sidecar Container Lifecycle in kubernetes/kubernetes

### The Problem

Kubernetes added native sidecar containers (KEP-753) but the lifecycle management is incomplete. Sidecar containers don't properly:
- Receive pre-stop hooks before the main container terminates
- Report readiness independently from the main container
- Respect shutdown ordering (sidecars should terminate after main containers)

### objective.md

```markdown
# Objective
Implement proper lifecycle management for native sidecar containers in kubernetes/kubernetes

# Sub-objectives
- [ ] Sidecar containers receive pre-stop hooks before main container termination
- [ ] Sidecar readiness is tracked independently and exposed in pod status
- [ ] Shutdown ordering: main containers terminate first, then sidecars in reverse init order
- [ ] Kubelet respects terminationGracePeriodSeconds per sidecar independently

# Acceptance Criteria
- All existing e2e tests in test/e2e/common/node pass
- New e2e test: sidecar pre-stop hook fires before main container stops
- New e2e test: pod status shows per-sidecar readiness
- New e2e test: sidecars outlive main containers during shutdown
- No >2% increase in pod startup latency (node_perf benchmark)
- kubectl describe pod shows sidecar lifecycle status

# Constraints
- Do not break backward compatibility with existing pod specs
- Sidecar feature gate must remain respected
- No changes to the API server or etcd schema in this iteration
```

### What Tvastr Does With This

**Forge Master** reads the objective, sees 3 sub-objectives, spawns 3 agents. Each agent:

1. Reads kubernetes/kubernetes's README.md, CONTRIBUTING.md, and Makefile
2. Discovers build commands (`make quick-release-images`), test commands (`go test`, `make test-e2e-node`)
3. Understands the repo structure from docs and code exploration
4. Works on its sub-objective using discovered build/test commands

| Agent | Sub-objective | Works on | Discovers |
|-------|--------------|----------|-----------|
| Agent 1 | Pre-stop hooks + shutdown ordering | Lifecycle logic | `make`, `go test ./pkg/kubelet/...` |
| Agent 2 | Independent readiness tracking | Status reporting | API types, kubelet status |
| Agent 3 | Test coverage + perf validation | Verification | `make test-e2e-node`, benchmark scripts |

No Docker adapter. No Kubernetes adapter. No builder abstraction. The agents read the repo and run the right commands.

---

## Core Components

### 1. Forge Master (Orchestrator)

Built on **Claude Agent SDK**. The brain of the operation.

**Responsibilities:**
- Parse `objective.md` and decompose into independent sub-objectives
- Spawn forge agents (one per sub-objective, run in parallel)
- Coordinate shared resources (one cluster, one repo)
- Merge patches: agent A's changes + agent B's changes must coexist
- Conflict resolution: if agent B's patch breaks agent A's passing tests, forge master mediates
- Decide when the overall objective is met

**What it does NOT do:**
- Build code (agent's job)
- Run tests (agent's job)
- Deploy (agent's job)
- Know anything about Docker, Kubernetes, or any specific toolchain

**Why Claude Agent SDK:** Native tool-use, multi-turn conversations, session management. The forge master itself is an agent that spawns child agents — the SDK's architecture supports this cleanly.

### 2. Forge Agent (Worker)

Each agent owns one sub-objective and runs the forge loop independently:

```
DISCOVER → PLAN → PATCH → VALIDATE → keep/revert → repeat
  ↑                                         │
  └───────── revert + learn ◄──────────────┘
```

**Phase details:**

| Phase | What happens | On failure |
|-------|-------------|------------|
| **DISCOVER** | Read repo docs (README, CLAUDE.md, Makefile, CI configs). Learn how to build, test, deploy. | Ask forge master for guidance |
| **PLAN** | Read objective + journal + repo state + other agents' patches. Produce a patch plan. | — |
| **PATCH** | Edit code on a git branch (`tvastr/agent-N/iter-M`). | — |
| **VALIDATE** | Run build + tests using commands discovered from repo docs. Fail-fast. | Revert, log which tests failed and why, re-plan |

The DISCOVER phase happens once at the start (and the agent caches what it learns). Subsequent iterations go straight to PLAN.

**Agent tools:**
- `read_file`, `write_file`, `edit_file` — code manipulation
- `list_files`, `search_code` — code exploration
- `run_command` — execute any shell command (build, test, deploy, git, etc.)
- `journal_read` — query past iterations (own + other agents')
- `journal_write` — log current iteration result
- `claim_lock` / `release_lock` — coordinate shared resources

Note: there is no `build` or `deploy` tool. The agent uses `run_command` with whatever commands it discovered from the repo's docs. This is intentional — tvastr doesn't need to know what "building" means for any specific repo.

### 3. SQLite State Store

Single database, shared by all agents. Why SQLite: zero-config, file-based, handles concurrent reads well, WAL mode for concurrent writes from multiple agents.

**Schema:**

```sql
-- Sub-objectives decomposed from objective.md
CREATE TABLE sub_objectives (
  id            INTEGER PRIMARY KEY,
  description   TEXT NOT NULL,
  status        TEXT DEFAULT 'pending',  -- pending | in_progress | done | blocked
  assigned_agent TEXT,
  priority      INTEGER DEFAULT 0,
  depends_on    TEXT,                    -- JSON array of sub_objective ids
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at  TIMESTAMP
);

-- Every iteration every agent runs
CREATE TABLE iterations (
  id                    INTEGER PRIMARY KEY,
  agent_id              TEXT NOT NULL,
  sub_objective_id      INTEGER REFERENCES sub_objectives(id),
  iteration_num         INTEGER NOT NULL,
  hypothesis            TEXT,
  files_changed         TEXT,            -- JSON array
  patch_sha             TEXT,
  validate_results      TEXT,            -- JSON: [{name, status, output, duration}]
  outcome               TEXT NOT NULL,   -- advanced | reverted | partial
  lesson                TEXT,            -- structured failure reason
  created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prevent two agents deploying simultaneously
CREATE TABLE resource_locks (
  resource    TEXT PRIMARY KEY,
  agent_id    TEXT NOT NULL,
  acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at  TIMESTAMP NOT NULL
);

-- Performance baselines for regression detection
CREATE TABLE baselines (
  test_name   TEXT NOT NULL,
  metric      TEXT NOT NULL,
  value       REAL NOT NULL,
  measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  patch_sha   TEXT,
  PRIMARY KEY (test_name, metric)
);
```

### 4. Multi-Agent Coordination

Three strategies, chosen per-run:

**Strategy A: Isolated branches, sequential merge (default)**
- Each agent works on its own branch
- When agent A passes all validations, forge master merges to `tvastr/main`
- Agent B rebases onto new `tvastr/main` before its next iteration
- Simple, safe, slower

**Strategy B: Shared branch, file-level locking**
- Agents claim files/directories before editing
- No two agents touch the same file simultaneously
- Faster, requires good sub-objective decomposition

**Strategy C: Speculative parallel, validate-then-merge**
- All agents work in parallel on separate branches
- Forge master periodically attempts combined merge + full validation
- If combined build/test fails, bisect which agent's patch broke it
- Fastest, most complex

**Resource coordination:**
- Only one agent deploys at a time (resource lock)
- Agents queue for deploy access via SQLite locks
- Lock has TTL to prevent deadlocks from crashed agents

### 5. Web UI (React + WebSocket)

Serves two purposes: **monitoring** long-running forge sessions and **steering** mid-run.

**Views:**

| View | What it shows |
|------|--------------|
| **Dashboard** | Active agents, current iteration per agent, overall progress toward acceptance criteria |
| **Agent Stream** | Live terminal output per agent — LLM reasoning, build logs, test output (WebSocket) |
| **Iteration Timeline** | Visual history of all iterations across agents, color-coded pass/fail/revert |
| **Patch Viewer** | Side-by-side diff of what each agent changed per iteration |
| **Test Results** | Expandable test output, filterable by tier (functional/regression/performance) |
| **Journal** | Searchable table of all iterations with structured failure lessons |
| **Controls** | Pause/resume agents, edit objective mid-run, force revert, kill agent |

**Why WebSocket:** Forge runs last hours. Live streaming of agent reasoning + build output + test results is essential. Each agent maintains its own WebSocket channel.

**Tech:** FastAPI backend, React 18 + TypeScript frontend, TanStack Query for state, Tailwind CSS.

---

## The Multi-Agent Flow

```
Human writes objective.md
         │
    Forge Master reads it
         │
    Decomposes into N sub-objectives
         │
    ┌────┼────┐
    ▼    ▼    ▼
  Agent1 Agent2 Agent3    ← parallel, own branches
    │    │    │
    │    │    │  each: DISCOVER repo docs → PLAN → PATCH → VALIDATE
    │    │    │  (agents figure out build/test from repo's own docs)
    │    │    │
    ▼    ▼    ▼
  Pass?  Pass?  Pass?
    │    │    │
    └────┼────┘
         │
    Forge Master merges all passing patches
         │
    Combined validation on merged result
         │
    Pass? → Done. Output final patch set.
    Fail? → Identify conflicting patch → reassign to agent → loop
```

**Key insight:** Individual agent success ≠ combined success. The forge master's job is to handle the integration layer that no single agent sees.

---

## Safety Rails

| Rail | What it does |
|------|-------------|
| **Max iterations** | Per-agent cap (default: 50) |
| **Max wall time** | Total run cap (default: 8 hours) |
| **Rollback-first** | Any failure triggers revert before retrying |
| **Human checkpoint** | Optionally pause after every N iterations for review |
| **Cost tracking** | Log LLM tokens + compute cost per iteration. Abort if budget exceeded. |
| **Blast radius control** | Agents can only modify files under the target repo |
| **Command allowlist** | Optional: restrict what commands agents can run |

---

## Iteration Intelligence

The agent doesn't blindly retry. Each planning phase uses:

1. **Objective** from `objective.md`
2. **Full failure history** from the journal (own + other agents')
3. **Current repo state** (diff from upstream)
4. **Repo documentation** discovered in the DISCOVER phase
5. **Strategy rules** encoded in the system prompt:
   - If the last 3 iterations failed on the same test → step back, reconsider approach
   - If regression tests fail → fix those before advancing the feature
   - If build fails → likely syntax/import error, small fix
   - After 5 failed iterations → propose alternative architecture to forge master
   - If another agent's merged patch changed your assumptions → re-read affected files

---

## Directory Structure

```
tvastr/
├── README.md
├── pyproject.toml
├── tvastr/
│   ├── __init__.py
│   ├── cli.py                  # CLI entry point
│   ├── master/
│   │   ├── orchestrator.py     # Forge Master agent
│   │   ├── decomposer.py      # Objective → sub-objectives
│   │   ├── merger.py           # Patch merge + conflict resolution
│   │   └── scheduler.py       # Agent spawn + coordination
│   ├── agent/
│   │   ├── forge_agent.py      # Forge Agent loop
│   │   ├── discovery.py        # Repo discovery (read docs, infer build/test)
│   │   └── tools.py            # Tool definitions
│   ├── infra/
│   │   └── validator.py        # Generic command runner + result parser
│   ├── state/
│   │   ├── db.py               # SQLite schema + queries
│   │   ├── journal.py          # Journal read/write helpers
│   │   └── locks.py            # Resource locking
│   ├── server/
│   │   ├── app.py              # FastAPI server
│   │   ├── ws.py               # WebSocket handlers
│   │   └── routes/
│   │       ├── agents.py
│   │       ├── iterations.py
│   │       └── controls.py
│   └── prompts/
│       ├── master_system.md    # Forge Master system prompt
│       ├── agent_system.md     # Forge Agent system prompt
│       └── templates/
│           ├── plan.md
│           ├── patch.md
│           └── debug.md
├── ui/                         # React frontend
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── AgentStream.tsx
│   │   │   ├── Timeline.tsx
│   │   │   ├── PatchViewer.tsx
│   │   │   └── Controls.tsx
│   │   └── hooks/
│   │       └── useWebSocket.ts
│   └── package.json
├── examples/
│   ├── k8s-sidecar-lifecycle/
│   │   ├── objective.md
│   │   └── repo.yaml           # optional hints
│   ├── redis-cluster-fix/
│   │   ├── objective.md
│   │   └── repo.yaml
│   └── python-lib-feature/
│       ├── objective.md
│       └── repo.yaml
└── .tvastr/
    └── tvastr.db
```

Note: no `infra/builder.py`, no `infra/deployer.py`, no `infra/adapters/`. The agent handles all of that by reading the repo's documentation and running commands directly.

---

## Build Phases

| Phase | What | Deliverable | Agent support |
|-------|------|-------------|---------------|
| **P1** | Single agent, local repo | CLI + forge loop + SQLite journal + agent-driven discovery. Agent reads repo docs to learn how to build/test. | 1 agent |
| **P2** | Multi-agent with forge master | Orchestrator, decomposer, merge strategies, locking. Test with N agents on a real repo. | N agents |
| **P3** | Web UI | FastAPI + WebSocket + React dashboard with live streaming and controls. | N agents |
| **P4** | Battle test | End-to-end on kubernetes/kubernetes with the sidecar lifecycle objective. Agent discovers k8s build/test/deploy from k8s docs. | N agents |

**What changed from the original plan:**
- **Removed P2 (Docker Build) and P3 (Kubernetes)** — no built-in builder/deployer abstractions. Agents discover how to build and deploy from the repo's own docs.
- **4 phases instead of 6** — simpler, faster to ship.
- **No Docker or Kubernetes dependency in tvastr itself** — tvastr is pure Python + SQLite. The target repo may use Docker/K8s, but that's the agent's problem to figure out.

---

## Inspirations

| Project | What we borrow | What we do differently |
|---------|---------------|----------------------|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | Iterative loop with automatic revert on regression. Fixed budget per iteration. Human steers via markdown. | Multi-signal validation (not single metric). Multi-agent. Agent-driven discovery. |
| [AutoForgeAI/autoforge](https://github.com/AutoForgeAI/autoforge) | Claude Agent SDK + MCP tools. SQLite for state. WebSocket UI for streaming. | Not greenfield — patches existing repos. Revert-on-failure. No hardcoded build/deploy — agents discover from docs. |
