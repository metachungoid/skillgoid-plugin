#CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code plugin (`skillgoid`) packaged in a single subdirectory: `skillgoid-plugin/`. The outer `skillgoid/` directory only contains this one plugin — treat `skillgoid-plugin/` as the project root. The plugin manifest is `skillgoid-plugin/.claude-plugin/plugin.json`.

## Common commands

Run from `skillgoid-plugin/`:

- `make test` (or `pytest`) — full suite, configured via `pyproject.toml` (`testpaths = ["tests"]`, fixtures under `tests/fixtures/` are deliberately excluded from collection).
- `pytest tests/test_measure_python.py::test_name` — run a single test.
- `make lint` (or `ruff check .`) — line length 100, `T201` (no `print`) is enabled repo-wide, relaxed only for `tests/fixtures/**`.
- `make install-local` — `claude plugin install .` for local plugin testing.

Python: requires >=3.11. Dev deps (`pytest`, `pyyaml`, `jsonschema`, `ruff`, `mypy`) live in the `[project.optional-dependencies].dev` group.

## Architecture

Skillgoid is a **criteria-gated autonomous build loop**. The plugin orchestrates building a user's project inside their CWD by iterating build → measure → reflect until declared gates pass, then curating lessons into a user-global vault.

### Pipeline (driven by `skills/build/SKILL.md`)

```
retrieve → clarify → feasibility → plan → (per-chunk wave) loop → integration → retrospect
```

- **retrieve** — reads `~/.claude/skillgoid/vault/<language>-lessons.md`, filters by current plugin version via `scripts/vault_filter.py`, surfaces relevant lessons to the main session.
- **clarify** — interactive; writes `.skillgoid/goal.md` and `.skillgoid/criteria.yaml` (validated against `schemas/criteria.schema.json`).
- **feasibility** — pre-flights every gate against the environment before iteration budget burns.
- **plan** — writes `.skillgoid/blueprint.md` and `.skillgoid/chunks.yaml` (validated against `schemas/chunks.schema.json`). Blueprint `## headings` are expected to map 1:1 to chunk ids.
- **build** — computes execution waves via `scripts/chunk_topo.py` (topological sort of `depends_on`), dispatches chunks in each wave concurrently via the Agent tool, waits for the whole wave before evaluating. Parallel sibling chunks require emitting all `Agent()` tool calls in a single message.
- **loop** (one per chunk, runs inside a subagent) — build, then invokes the language-gates adapter skill, then writes `.skillgoid/iterations/NNN.json`. Exit conditions evaluated in order: success, budget_exhausted, stalled (hash-equality of `failure_signature` from `scripts/stall_check.py` — never judgment-based).
- **retrospect** — writes `.skillgoid/retrospective.md`, curates `notable: true` iterations into the user-global vault, appends one JSON line to `~/.claude/skillgoid/metrics.jsonl`.
- **unstick / stats** — recovery/observability skills invokable directly.

### Skills vs scripts

**Skills are prose; scripts are code.** `skills/*/SKILL.md` are YAML-frontmatter markdown procedures; non-trivial logic lives in `scripts/*.py` and the skill shells out. When adding behavior, prefer growing a script and referencing it from the skill — don't embed logic in the prose.

### Gate adapter contract

`skills/python-gates/SKILL.md` wraps `scripts/measure_python.py`, which is the reference language adapter. The contract (see `docs/custom-adapter-template.md`) is:

- **Input:** project path + a filtered `criteria.yaml` subset (via stdin or temp file).
- **Output (stdout):** `{"passed": bool, "results": [{"gate_id", "passed", "stdout", "stderr", "hint"}]}` — always valid JSON, even on partial failure. Exit code 0 all-passed, 1 any-failed, 2 internal error.
- **Supported gate types:** `pytest`, `ruff`, `mypy`, `import-clean`, `cli-command-runs`, `run-command`, `coverage`. Unsupported types must emit a failed result with `hint: "unsupported gate type: <type>"` — never invent workarounds.

Adding a new language: write `skills/<language>-gates/SKILL.md` and usually a companion `scripts/measure_<language>.py` that honors the same JSON contract.

### State locations

- Project-local: `.skillgoid/` in the user's CWD — `goal.md`, `criteria.yaml`, `blueprint.md`, `chunks.yaml`, `iterations/NNN.json`, `integration/<attempt>.json`, `retrospective.md`.
- User-global: `~/.claude/skillgoid/vault/<language>-lessons.md`, `~/.claude/skillgoid/vault/meta-lessons.md`, `~/.claude/skillgoid/metrics.jsonl`.
- Both `chunks.yaml`, `criteria.yaml`, and `iterations/NNN.json` have JSON Schemas in `schemas/` that every writer must satisfy.

### Hooks

`hooks/hooks.json` wires two bash hooks; both must be robust to missing `.skillgoid/` and should never crash the session:

- **SessionStart → `detect-resume.sh`** — if CWD contains `.skillgoid/`, emits a resume summary via `hookSpecificOutput.additionalContext`. Has a PyYAML-optional regex fallback for chunk counting.
- **Stop → `gate-guard.sh`** — blocks Stop mid-loop when the latest iteration has failing gates AND loop budget remains. Returns `{"decision": "block", "reason": ...}` with the top-2 failing gate hints surfaced. Same PyYAML-optional fallback pattern.

## Conventions worth knowing

- **`$SKILLGOID_PYTHON`.** The adapter always exports `SKILLGOID_PYTHON=sys.executable` into gate subprocesses. Inside shell command strings like `["bash", "-c", "..."]`, use `$SKILLGOID_PYTHON`, not bare `python` — the bare-`python` auto-resolution (v0.4) only rewrites `command[0]`, not substrings inside shell bodies.
- **Backward compatibility.** Every release since v0.2 has been additive and backward-compatible with existing projects — preserve that invariant when changing schemas, iteration file shape, or skill inputs.
- **Wave dispatch.** When a wave has multiple chunks, emit every `Agent()` call in a single assistant message so they run in parallel; sequential messages serialize them.
- **Stall detection is deterministic.** Never compare iteration failure modes "by eye" — always go through `scripts/stall_check.py` so behavior matches what the loop actually branches on.
- **The `notable: true` flag** on an iteration is what promotes a reflection into the vault during retrospect. Use it sparingly — boring iterations stay `notable: false`.
