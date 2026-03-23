# Tvastr

> *Named after the Vedic divine craftsman who forged the weapons of the gods.*

Autonomous code forge that iteratively patches, validates, and learns from failure — powered by Claude.

Give it an objective and a repo. It loops **PLAN → PATCH → VALIDATE**, reverting on failure, learning from each attempt, until the objective is met or the budget runs out. No human in the loop. No blind retries. Every iteration reads the full failure journal before planning the next move.

```
Iteration 1  [FAIL]  Created Matrix class, missed __getitem__
Iteration 2  [FAIL]  Added __getitem__, broke transpose
Iteration 3  [PASS]  Fixed transpose, all 17 tests green
```

---

## Why Tvastr

Most AI coding tools generate code once and hand it back. Tvastr **keeps going**.

- It writes code, runs your tests, reads the failures, reverts the bad patch, and tries again with that failure burned into its context.
- It never makes the same mistake twice — every past iteration's hypothesis, outcome, and lesson feed into the next planning phase.
- It works against **your test suite** as the source of truth, not vibes.

The forge loop is simple but powerful: if the tests pass, the patch stays. If they fail, it's reverted and the agent sees exactly what went wrong.

---

## How It Works

```
                    ┌──────────────┐
                    │  objective.md │  ← you write this
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Forge Agent  │  ← Claude with tools
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           PLAN         PATCH       VALIDATE
        (read code,   (edit files   (run tests,
         read journal,  via tools)   fail-fast)
         form hypothesis)
              │            │            │
              │            │     ┌──────┴──────┐
              │            │     ▼             ▼
              │            │   PASS          FAIL
              │            │   keep patch    revert + log
              │            │     │             │
              │            │     ▼             ▼
              │            │   Done?      Next iteration
              └────────────┴─────────────────┘
                                │
                         ┌──────▼──────┐
                         │  SQLite DB   │  ← iteration journal,
                         │  (.tvastr/)  │    baselines, locks
                         └─────────────┘
```

**The agent has tools**, not just text generation. It can read files, write files, search code, and run commands — all sandboxed to the target repo. It reads before it edits. It explores before it patches.

**The journal is the memory.** Every iteration records: what was tried (hypothesis), what changed (files + patch SHA), what happened (test results), and what was learned (structured lesson). The agent reads the last 10 iterations before planning each move.

---

## Quick Start

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)

### Install

```bash
# Clone
git clone https://github.com/yourusername/tvastr.git
cd tvastr

# Install
pip install -e .

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Run the Example

Tvastr ships with a sample objective: add a `Matrix` class to a tiny math library, validated by 17 pre-written tests.

```bash
# Initialize the example repo (creates .tvastr/ config)
tvastr init --repo examples/python-lib-feature/mathforge-repo

# Run the forge
tvastr run \
  --objective examples/python-lib-feature/objective.md \
  --repo examples/python-lib-feature/mathforge-repo \
  --config examples/python-lib-feature/mathforge-repo/.tvastr/repo.yaml \
  --max-iterations 10
```

Watch it work:

```
╭─ Tvastr ──────────────────────────────────────────────╮
│ Objective:                                             │
│ Add a Matrix class to the mathforge library that...    │
╰────────────────────────────────────────────────────────╯
╭─ Starting Forge ──────────────────────────────────────╮
│ Tvastr Forge Agent — forge-1                           │
│ Repo: /path/to/mathforge-repo                          │
│ Max iterations: 10                                     │
╰────────────────────────────────────────────────────────╯
──────────────── Iteration 1 ────────────────
  → list_files(.)
  → read_file(mathforge/vector.py)
  → read_file(tests/test_matrix.py)
  → write_file(mathforge/matrix.py, 2847 chars)
  → read_file(mathforge/__init__.py)
  → edit_file(mathforge/__init__.py, edit)
Running validation...
All validations passed! (3.2s)
╭────────────────────────────────────────────────────────╮
│ Objective met after 1 iterations!                      │
╰────────────────────────────────────────────────────────╯
```

### View the Journal

```bash
tvastr journal --repo examples/python-lib-feature/mathforge-repo
```

```
╭─ Iteration 1 — forge-1 ──────────────────────────────╮
│ Hypothesis: Created Matrix class with all required...  │
│ Files: ["mathforge/__init__.py", "mathforge/matrix.py"]│
│ Outcome: advanced                                      │
│ Lesson: Changes validated successfully.                │
╰────────────────────────────────────────────────────────╯
```

---

## Usage

### 1. Write an Objective

Create an `objective.md` describing what you want built or fixed:

```markdown
# Objective
Add retry logic with exponential backoff to the HTTP client

# Acceptance Criteria
- Retries up to 3 times on 5xx responses
- Backoff doubles each attempt (1s, 2s, 4s)
- All existing tests pass
- New tests cover retry behavior and backoff timing

# Constraints
- Do not add new dependencies
- Do not change the public API
```

### 2. Configure Validation

Create `.tvastr/repo.yaml` in your target repo (or run `tvastr init`):

```yaml
repo: my-project
language: python

validate:
  functional:
    - name: new-feature-tests
      command: pytest tests/test_retry.py -v
      timeout: 60
  regression:
    - name: existing-tests
      command: pytest tests/ -v --ignore=tests/test_retry.py
      timeout: 120
```

The validation tiers run in order — **functional** first, then **regression**, then **performance**. If any tier fails, the rest are skipped (fail-fast).

### 3. Run the Forge

```bash
tvastr run \
  --objective objective.md \
  --repo /path/to/your/repo \
  --max-iterations 20 \
  --model claude-sonnet-4-20250514
```

| Flag | Default | Description |
|------|---------|-------------|
| `--objective, -o` | *(required)* | Path to objective.md |
| `--repo, -r` | *(required)* | Path to target repo |
| `--config, -c` | `.tvastr/repo.yaml` | Path to repo config |
| `--max-iterations, -n` | `50` | Iteration budget |
| `--model, -m` | `claude-sonnet-4-20250514` | Claude model ID |
| `--agent-id` | `forge-1` | Agent identifier |

### 4. Inspect Results

```bash
# View iteration history
tvastr journal --repo /path/to/your/repo

# Filter by agent
tvastr journal --repo /path/to/your/repo --agent-id forge-1

# Limit output
tvastr journal --repo /path/to/your/repo --limit 5
```

The forge commits each successful iteration to git with the message `tvastr: iteration N` and the agent's hypothesis. Failed iterations are reverted — your repo stays clean.

---

## How the Agent Thinks

The agent isn't a one-shot code generator. It's an **iterative reasoner** with memory.

**Iteration 1** — explores the codebase, reads the objective, makes a first attempt.

**Iteration 2+** — reads the journal first. Sees what it tried, what failed, and why. Plans around past failures.

**After 3 consecutive failures on the same issue** — the system prompt instructs it to try a fundamentally different approach.

**After 10+ failures** — it steps back and reconsiders the entire strategy.

The agent prompt enforces discipline:
- Always read a file before editing it
- Make small, focused changes per iteration
- Never refactor unrelated code
- Form a clear hypothesis before patching

---

## Agent Tools

The forge agent has six tools available during each iteration:

| Tool | What it does |
|------|-------------|
| `read_file` | Read file contents (with line numbers) |
| `write_file` | Create or overwrite a file |
| `edit_file` | Find-and-replace a specific string in a file |
| `list_files` | List directory contents with glob filtering |
| `search_code` | Grep the codebase for a pattern |
| `run_command` | Execute a shell command (with safety blocks) |

All file operations are sandboxed to the target repo. Path traversal is blocked. Dangerous shell commands (`rm -rf /`, etc.) are rejected.

---

## State & Persistence

Everything is stored in `.tvastr/tvastr.db` (SQLite, WAL mode):

| Table | Purpose |
|-------|---------|
| `iterations` | Full history — hypothesis, files changed, patch SHA, build/test results, outcome, lessons |
| `sub_objectives` | Decomposed goals (used in multi-agent mode) |
| `resource_locks` | Coordination locks with TTL (used in multi-agent mode) |
| `baselines` | Performance baselines for regression detection |

The database is the forge's long-term memory. Agents query it to avoid repeating past mistakes.

---

## Example: The Bundled Demo

The repo includes a complete working example:

```
examples/python-lib-feature/
├── objective.md                    # "Add a Matrix class"
└── mathforge-repo/
    ├── mathforge/
    │   ├── __init__.py
    │   └── vector.py              # Existing code (must not break)
    ├── tests/
    │   ├── test_vector.py         # Regression tests
    │   └── test_matrix.py         # 17 target tests (agent must make these pass)
    └── .tvastr/
        └── repo.yaml              # Validation config
```

**The objective:** implement a `Matrix` class supporting creation, addition, multiplication, transpose, determinant, and repr — all in pure Python, without breaking the existing `Vector` class.

**The tests already exist.** The agent's job is to write the code that makes them pass. This is the core pattern: tests as specification, agent as implementer.

---

## Architecture

```
tvastr/
├── cli.py                # Click CLI — run, journal, init
├── agent/
│   ├── forge_agent.py    # The forge loop (plan → patch → validate → learn)
│   └── tools.py          # Tool definitions + sandboxed execution
├── infra/
│   ├── validator.py      # Test runner with fail-fast and result parsing
│   └── adapters/         # (Future: kubernetes, docker-compose, local)
├── state/
│   └── db.py             # SQLite state store — iterations, locks, baselines
└── prompts/
    └── agent_system.md   # Agent system prompt (iteration-aware instructions)
```

---

## Roadmap

Tvastr is built in phases. **P1 is complete** — single agent, local repo, test-driven forge loop.

| Phase | What | Status |
|-------|------|--------|
| **P1** | Single agent, local repo, pytest validation | Done |
| **P2** | Docker build + local deploy | Planned |
| **P3** | Kubernetes deploy + 3-tier validation (functional/regression/perf) | Planned |
| **P4** | Multi-agent with Forge Master orchestrator | Planned |
| **P5** | Web UI — live agent streams, iteration timeline, patch viewer | Planned |
| **P6** | Battle test on kubernetes/kubernetes | Planned |

The full architecture plan (multi-agent coordination, merge strategies, Web UI design) is in [`TVASTR_PLAN.md`](TVASTR_PLAN.md).

---

## Inspirations

| Project | What we took | How Tvastr differs |
|---------|-------------|-------------------|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | Iterative loop with auto-revert on regression. Fixed budget. Human steers via markdown. | Multi-signal validation (not single metric). Deploys to live infra. Multi-agent coordination. |
| [AutoForgeAI/autoforge](https://github.com/AutoForgeAI/autoforge) | Claude Agent SDK + MCP tools. SQLite for state. WebSocket UI for streaming. | Patches existing repos, not greenfield. Deploys to real clusters. Revert-on-failure, not skip-and-retry. |

---

## Stack

- **Python 3.11+** — core runtime
- **Anthropic SDK** — Claude API with tool use
- **Click** — CLI framework
- **Rich** — terminal UI (panels, syntax highlighting, progress)
- **SQLite** — state store (WAL mode for concurrent access)
- **PyYAML** — config parsing

---

## License

MIT
