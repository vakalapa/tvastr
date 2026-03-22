# TVASTR

> *Named after the Vedic divine craftsman who forged the weapons of the gods.*

Autonomous craftsman that forges, deploys, and validates code changes against live infrastructure. Give it an objective, a repo, and a cluster — it iterates until the objective is met or it exhausts its budget.

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
│ Sidecar  │  │ Kubelet  │  │  Perf       │
│ lifecycle│  │ hooks    │  │  tuning     │
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
│              INFRASTRUCTURE LAYER                         │
│  Build → Deploy → Validate (shared cluster)              │
└─────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│              WEB UI (React + WebSocket)                   │
│  • Live agent streams   • Iteration timeline             │
│  • Test results grid    • Patch diff viewer              │
└─────────────────────────────────────────────────────────┘
```

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

### .tvastr/repo.yaml

```yaml
repo: github.com/kubernetes/kubernetes
language: go

build:
  command: make quick-release-images
  artifact: registry.local:5000/kube-node:tvastr-{{agent}}-{{iter}}
  components:
    - cmd/kubelet
    - cmd/kube-apiserver
    - cmd/kube-controller-manager

deploy:
  type: kubernetes
  cluster: kubeconfig://~/.kube/tvastr-cluster
  strategy: kind-reload    # rebuild kind node image
  kind:
    config: .tvastr/kind-config.yaml
    node_image: "{{artifact}}"
  health_check:
    command: kubectl get nodes -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}'
    expect: "True"
    timeout: 5m

validate:
  functional:
    - name: sidecar-lifecycle
      command: go test ./test/e2e/common/... -run TestSidecarLifecycle -count=1
      timeout: 15m
    - name: sidecar-readiness
      command: go test ./test/e2e/common/... -run TestSidecarReadiness -count=1
      timeout: 10m
  regression:
    - name: node-e2e
      command: make test-e2e-node FOCUS="Container|Sidecar|Lifecycle"
      timeout: 30m
    - name: unit-kubelet
      command: go test ./pkg/kubelet/... -count=1 -timeout=20m
      timeout: 25m
  performance:
    - name: pod-startup-latency
      command: ./test/e2e/benchmarks/pod_startup.sh
      threshold: "p99_startup_ms <= 1.02 * baseline"
    - name: density-100-pods
      command: go test ./test/e2e/benchmarks/... -run TestDensity100 -count=1
      threshold: "avg_latency_ms <= 1.02 * baseline"

agents:
  max_parallel: 3
  merge_strategy: sequential
  file_boundaries:
    agent_1: ["pkg/kubelet/kuberuntime/kuberuntime_container_lifecycle.go", "pkg/kubelet/kuberuntime/kuberuntime_manager.go"]
    agent_2: ["pkg/kubelet/status/", "staging/src/k8s.io/api/core/v1/types.go"]
    agent_3: ["test/e2e/common/", "test/e2e/benchmarks/"]
```

### What Tvastr Does With This

**Forge Master** reads the objective, sees 3 sub-objectives, spawns 3 agents:

| Agent | Sub-objective | Files | Works on |
|-------|--------------|-------|----------|
| Agent 1 | Pre-stop hooks + shutdown ordering | kubelet runtime | Lifecycle logic |
| Agent 2 | Independent readiness tracking | kubelet status + API types | Status reporting |
| Agent 3 | Test coverage + perf validation | e2e tests + benchmarks | Verification |

Agent 3 intentionally runs slightly behind — it writes tests against the interfaces agents 1 and 2 are building, validating their work.

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

**Why Claude Agent SDK:** Native tool-use, multi-turn conversations, session management. The forge master itself is an agent that spawns child agents — the SDK's architecture supports this cleanly.

### 2. Forge Agent (Worker)

Each agent owns one sub-objective and runs the forge loop independently:

```
PLAN → PATCH → BUILD → DEPLOY → VALIDATE
  ↑                                    │
  └────── revert + learn ◄────────────┘
```

**Phase details:**

| Phase | What happens | On failure |
|-------|-------------|------------|
| **PLAN** | Read objective + journal + cluster state + other agents' patches. Produce a patch plan. | — |
| **PATCH** | Edit code on a git branch (`tvastr/agent-N/iter-M`). | — |
| **BUILD** | Run repo's build command. Produce artifact. | Revert, log compile error, re-plan |
| **DEPLOY** | Push artifact to cluster. Wait for healthy rollout. | Rollback, revert, log deploy error |
| **VALIDATE** | Run 3 tiers: functional → regression → performance (fail-fast). | Revert, log which tests failed and why, re-plan |

**Agent tools (exposed via MCP server):**
- `file_read`, `file_write`, `file_search` — code manipulation
- `git_*` — branch, commit, diff, log
- `kubectl_read` — get, describe, logs (read-only, no mutations)
- `build` — trigger build pipeline
- `deploy` — trigger deploy pipeline
- `run_test` — execute a specific validation tier
- `journal_read` — query past iterations (own + other agents')
- `journal_write` — log current iteration result
- `claim_lock` / `release_lock` — coordinate shared resources

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
  build_status          TEXT,            -- pass | fail | skip
  build_log             TEXT,
  build_duration_secs   INTEGER,
  deploy_status         TEXT,
  deploy_log            TEXT,
  deploy_duration_secs  INTEGER,
  validate_functional   TEXT,            -- JSON: {status, details}
  validate_regression   TEXT,
  validate_performance  TEXT,
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

Three strategies, chosen per-repo in `.tvastr/repo.yaml`:

**Strategy A: Isolated branches, sequential merge (default)**
- Each agent works on its own branch
- When agent A passes all validations, forge master merges to `tvastr/main`
- Agent B rebases onto new `tvastr/main` before its next iteration
- Simple, safe, slower

**Strategy B: Shared branch, file-level locking**
- Agents claim files/directories before editing (via `file_boundaries` config)
- No two agents touch the same file simultaneously
- Faster, requires good sub-objective decomposition

**Strategy C: Speculative parallel, validate-then-merge**
- All agents work in parallel on separate branches
- Forge master periodically attempts combined merge + full validation
- If combined build/test fails, bisect which agent's patch broke it
- Fastest, most complex

**Deploy coordination:**
- Only one agent deploys at a time (resource lock on cluster)
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
    │    │    │  (each running PLAN→PATCH→BUILD→DEPLOY→VALIDATE independently)
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
| **Cluster health gate** | Check cluster health before every deploy. Don't deploy to a broken cluster. |
| **Rollback-first** | Any deploy failure triggers rollback before revert |
| **Human checkpoint** | Optionally pause after every N iterations for review |
| **Cost tracking** | Log LLM tokens + compute cost per iteration. Abort if budget exceeded. |
| **Blast radius control** | Agents can only modify files under paths specified in `file_boundaries` |
| **No direct cluster mutation** | Agents get read-only kubectl. All changes go through build→deploy pipeline. |

---

## Iteration Intelligence

The agent doesn't blindly retry. Each planning phase uses:

1. **Objective** from `objective.md`
2. **Full failure history** from the journal (own + other agents')
3. **Current repo state** (diff from upstream)
4. **Cluster state** (pod status, logs, events)
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
│   │   ├── planner.py          # Iteration planning
│   │   ├── patcher.py          # Code editing
│   │   └── tools.py            # MCP tool definitions
│   ├── infra/
│   │   ├── builder.py          # Build abstraction
│   │   ├── deployer.py         # Deploy abstraction
│   │   ├── validator.py        # Test runner (3 tiers)
│   │   ├── rollback.py         # Revert + cluster rollback
│   │   └── adapters/
│   │       ├── kubernetes.py
│   │       ├── docker_compose.py
│   │       └── local.py
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
│   │   └── repo.yaml
│   ├── redis-cluster-fix/
│   │   ├── objective.md
│   │   └── repo.yaml
│   └── python-lib-feature/
│       ├── objective.md
│       └── repo.yaml
└── .tvastr/
    ├── repo.yaml
    └── tvastr.db
```

---

## Build Phases

| Phase | What | Deliverable | Agent support |
|-------|------|-------------|---------------|
| **P1** | Single agent, local repo, no deploy | CLI + forge loop + SQLite journal. Test against a Python lib with pytest. | 1 agent |
| **P2** | Docker build + local deploy | Builder + deployer (docker-compose adapter). Test against a containerized Go service. | 1 agent |
| **P3** | Kubernetes deploy + 3-tier validation | K8s adapter, validation framework, rollback. Test against a kind cluster. | 1 agent |
| **P4** | Multi-agent with forge master | Orchestrator, decomposer, merge strategies, locking. Test with 3 agents on k/k. | N agents |
| **P5** | Web UI | FastAPI + WebSocket + React dashboard with live streaming and controls. | N agents |
| **P6** | Battle test | End-to-end on kubernetes/kubernetes with the sidecar lifecycle objective. | N agents |

---

## Inspirations

| Project | What we borrow | What we do differently |
|---------|---------------|----------------------|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | Iterative loop with automatic revert on regression. Fixed budget per iteration. Human steers via markdown. | Multi-signal validation (not single metric). Live infra deployment. Multi-agent. |
| [AutoForgeAI/autoforge](https://github.com/AutoForgeAI/autoforge) | Claude Agent SDK + MCP tools. SQLite for state. WebSocket UI for streaming. | Not greenfield — patches existing repos. Deploys to real clusters. Revert-on-failure, not skip-and-retry. |
