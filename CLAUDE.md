# CLAUDE.md

## Project
Tvastr — autonomous craftsman that forges, deploys, and validates code changes against live infrastructure.

## Git Rules
- NEVER add `Co-Authored-By` lines to commits. All commits must be authored solely by the user.
- Do not add Claude as a commit author, co-author, or contributor in any form.

## Stack
- Python 3.11+, Anthropic SDK, Click, Rich, SQLite
- Target: Claude API with tool use for the forge agent loop

## Structure
- `tvastr/` — core package (cli, agent, infra, state)
- `examples/` — example repos and objectives for testing
- `TVASTR_PLAN.md` — full architecture plan
