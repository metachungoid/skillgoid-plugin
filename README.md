# Skillgoid

**A Claude Code plugin that turns a rough project goal into a shipped codebase through a criteria-gated autonomous build loop with compounding cross-project memory.**

- **Define success** — measurable gates, not vibes.
- **Build → measure → reflect** — loops until every gate passes.
- **Learn across projects** — a curated per-language lessons file grows smarter with every run.

```
/skillgoid:build "a Python CLI that syncs Notion tasks to a local JSON file"
```

## Contents

- [Install](#install)
- [Quickstart](#quickstart)
- [How it works](#how-it-works)
- [Commands](#commands)
- [Configuring gates](#configuring-gates)
- [State locations](#state-locations)
- [Context7 grounding](#context7-grounding)
- [Synthesizing gates from analogue repos](#synthesizing-gates-from-analogue-repos)
- [Custom language adapters](#custom-language-adapters)
- [Recovery](#recovery)
- [Development](#development)

---

## Install

```bash
git clone https://github.com/metachungoid/skillgoid-plugin.git
cd skillgoid-plugin
claude plugin install .
```

Or with make:

```bash
git clone https://github.com/metachungoid/skillgoid-plugin.git
cd skillgoid-plugin
make install-local
```

Requires Claude Code ≥ the current release. Python ≥ 3.11 must be on your PATH (used by the gate adapter and measurement scripts).

---

## Quickstart

**Start a new project from scratch:**

```
/skillgoid:build "a Flask REST API with SQLite persistence and pytest coverage"
```

Skillgoid will:

1. **Clarify** — ask a few focused questions to nail down scope, language, and success signals.
2. **Synthesize (optional)** — if you have an analogue repo to learn from, it can derive gates from observation.
3. **Feasibility** — pre-flight every gate against your environment before any iteration budget burns.
4. **Plan** — produce `blueprint.md` (architecture) and `chunks.yaml` (ordered build units).
5. **Build** — dispatch each chunk as a subagent, measure gates, reflect on failures, loop until gates pass or budget runs out.
6. **Retrospect** — write a `retrospective.md`, curate notable lessons into `~/.claude/skillgoid/vault/`, and append a metrics line.

**Resume after a session ends:**

```
/skillgoid:build resume
```

The `SessionStart` hook automatically detects an in-progress build when you open a directory containing `.skillgoid/` and injects a resume summary.

**Smoke-test your install:**

```bash
mkdir /tmp/sg-smoke && cd /tmp/sg-smoke
# then in Claude Code:
/skillgoid:build "a Python CLI that prints hello world with a --name flag"
```

---

## How it works

### The pipeline

```
retrieve → clarify → feasibility → plan → build loop → integration → retrospect
```

| Stage | What happens |
|---|---|
| **retrieve** | Reads `~/.claude/skillgoid/vault/<language>-lessons.md`, filters lessons by plugin version, surfaces relevant prior-project learnings. |
| **clarify** | Interactive Q&A — refines the goal, writes `.skillgoid/goal.md` and `.skillgoid/criteria.yaml`. |
| **feasibility** | Shallow-checks every gate's tools and commands against the live environment. Fails fast on missing binaries before wasting iteration budget. |
| **plan** | Writes `.skillgoid/blueprint.md` (architecture, type contracts, module responsibilities) and `.skillgoid/chunks.yaml` (build units with gate assignments and dependency order). Also dispatches the context7 fetcher to produce framework advisory grounding. |
| **build loop** | Topological sort of `chunks.yaml` → execution waves. Chunks in the same wave run in parallel (separate subagents). Each subagent builds, measures gates, reflects, writes an iteration record, loops until success/stall/budget. |
| **integration** | After all chunks pass, runs `integration_gates` (whole-system smoke tests). Up to 2 auto-repair retries. |
| **retrospect** | Synthesizes a retrospective, curates `notable: true` iterations into the vault, appends metrics. |

### Build loop detail

Each chunk runs a tight inner loop inside its own subagent:

```
build code → measure gates → reflect on failures → loop
```

Exit conditions, evaluated in order:
- **success** — all declared gates pass.
- **budget_exhausted** — `max_attempts` reached without success.
- **stalled** — `failure_signature` (16-char hex hash) matches the previous iteration's — the subagent is repeating the same failure. Deterministic; never judgment-based.

Every iteration writes `.skillgoid/iterations/<chunk_id>-NNN.json` (git-committed by default for free rollback targets). The `Stop` hook blocks accidental exits when gates are still failing.

### Parallel waves

Chunks with independent `depends_on` relationships run concurrently in the same wave. The orchestrator issues all of a wave's `Agent()` calls in a single message, waits for all to return, then evaluates gates across the whole wave before advancing.

---

## Commands

### Core

| Command | Purpose |
|---|---|
| `/skillgoid:build "<goal>"` | Start a new project. Runs the full pipeline from clarify through retrospect. |
| `/skillgoid:build resume` | Continue an in-progress build. Skips chunks that already succeeded. |
| `/skillgoid:build status` | Print chunk + iteration summary for the current project. |
| `/skillgoid:build retrospect-only` | Finalize the project as-is, even if not all gates passed. |

### Sub-skills (directly invokable)

| Command | Purpose |
|---|---|
| `/skillgoid:clarify` | Refine goal and draft `criteria.yaml` interactively. |
| `/skillgoid:feasibility` | Pre-flight gates against the environment. |
| `/skillgoid:plan` | Write `blueprint.md` + `chunks.yaml`. Accepts `--refresh-context7` to regenerate framework grounding. |
| `/skillgoid:synthesize-gates <repo-url-or-path>` | Derive `criteria.yaml` gates from an analogue reference repo. |
| `/skillgoid:unstick <chunk_id> "<hint>"` | Re-dispatch a stalled chunk with a one-sentence human hint injected into its prompt. |
| `/skillgoid:stats` | Cross-project metrics summary (success/stall rates, avg iterations). Reads `~/.claude/skillgoid/metrics.jsonl`. |
| `/skillgoid:explain` | Describe Skillgoid's concepts and pipeline interactively. |
| `/skillgoid:retrieve` | Manually surface vault lessons for a given goal. |
| `/skillgoid:retrospect` | Run the retrospect stage standalone (e.g. after manual edits). |

---

## Configuring gates

Gates live in `.skillgoid/criteria.yaml` and define what "done" means for each chunk and for the project as a whole.

### Minimal example

```yaml
language: python

loop:
  max_attempts: 5

gates:
  - id: lint
    type: ruff
    args: [check, .]

  - id: tests
    type: pytest
    args: [tests/]

  - id: typecheck
    type: mypy
    args: [src/]

  - id: cli_help
    type: cli-command-runs
    args: [myapp, --help]
    expect_stdout_match: "Usage:"

integration_gates:
  - id: cli_smoke
    type: cli-command-runs
    args: [myapp, version]
    expect_exit: 0

acceptance:
  - "Running `myapp sync` creates or updates tasks.json in the CWD."
  - "Running `myapp sync --dry-run` prints a diff without writing anything."
```

### Gate types

| Type | What it measures | Key fields |
|---|---|---|
| `pytest` | Test suite pass/fail | `args` (passed to pytest), `timeout` |
| `ruff` | Lint / style | `args` (e.g. `[check, .]`) |
| `mypy` | Static type checking | `args` (e.g. `[src/]`) |
| `import-clean` | Package imports without error | `module` or `args[0]` |
| `cli-command-runs` | CLI exits cleanly | `args` (argv list), `expect_exit`, `expect_stdout_match` |
| `run-command` | Arbitrary shell command exits cleanly | `command` (argv list), `expect_exit` |
| `coverage` | Test coverage threshold | `target`, `min_percent` (default 80), `compare_to_baseline` |

### Common fields

```yaml
gates:
  - id: tests              # unique identifier referenced by chunks
    type: pytest
    args: [tests/]
    timeout: 120           # seconds before the gate is killed and fails (default: 300)
    env:                   # extra env vars injected into the subprocess
      PYTHONPATH: src
```

> **Note on shell commands:** inside `run-command` or `cli-command-runs` command strings that use `bash -c`, reference `$SKILLGOID_PYTHON` instead of bare `python` — the adapter exports `SKILLGOID_PYTHON=sys.executable` into every gate subprocess.
>
> ```yaml
> command: ["bash", "-c", "$SKILLGOID_PYTHON -m myservice --port 8999 & sleep 1 && curl -sf localhost:8999/health && kill %1"]
> ```

### Model overrides

```yaml
models:
  chunk_subagent: sonnet    # default: sonnet
  integration_subagent: haiku
```

---

## State locations

### Project-local (`.skillgoid/`)

| File | Purpose |
|---|---|
| `goal.md` | Refined goal, scope, non-goals, success signals. Written by `clarify`. |
| `criteria.yaml` | Gates, acceptance scenarios, loop config. Written by `clarify` or `synthesize-gates`. |
| `blueprint.md` | Architecture, module responsibilities, cross-chunk type contracts. Written by `plan`. |
| `chunks.yaml` | Ordered build units with gate assignments, `depends_on`, `paths`. Written by `plan`. |
| `iterations/<chunk_id>-NNN.json` | Per-iteration records: exit reason, gate report, failure signature, changes. |
| `integration/<attempt>.json` | Integration gate results per attempt. |
| `retrospective.md` | End-of-project analysis, lessons, vault nominations. |
| `context7/framework-grounding.md` | Advisory framework idioms fetched from context7. Used by `plan` + `build`. |
| `context7/SKIPPED` | Sentinel written when context7 fetch failed or was skipped. |

### User-global (`~/.claude/skillgoid/`)

| Path | Purpose |
|---|---|
| `vault/<language>-lessons.md` | Curated per-language lessons from completed projects. Grows over time. |
| `vault/meta-lessons.md` | Cross-language architectural lessons. |
| `metrics.jsonl` | One JSON line per completed project — outcome, chunks, iterations, stalls, elapsed time. |

---

## Context7 grounding

When [context7](https://context7.com) is installed and configured in your Claude Code session, Skillgoid's `plan` skill fetches framework-specific advisory grounding before drafting the blueprint.

**What it does:** infers the primary framework from `goal.md` + manifest files (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`), queries context7 for idiomatic project structure, testing patterns, and common pitfalls, and writes `.skillgoid/context7/framework-grounding.md`. The `build` skill attaches this file to every per-chunk subagent prompt as advisory guidance.

**Installing context7:**

```bash
# requires a free API key from https://context7.com/dashboard
claude mcp add --transport http --scope user context7 \
  https://mcp.context7.com/mcp \
  --header "CONTEXT7_API_KEY: <your-key>"
# then fully restart Claude Code so the session picks up the new MCP
```

**Graceful degradation:** if context7 is not installed, quota is exceeded, or the framework can't be inferred, Skillgoid writes `.skillgoid/context7/SKIPPED` with a one-line reason and continues without grounding — the pipeline is unaffected.

**Refresh grounding:**

```bash
/skillgoid:plan --refresh-context7
```

Deletes the existing grounding file (and `SKIPPED` sentinel) and re-fetches. Hand-edits to `framework-grounding.md` persist across re-runs unless you pass this flag.

---

## Synthesizing gates from analogue repos

`synthesize-gates` derives a draft `criteria.yaml` by observing one or more reference repos, rather than authoring gates from scratch.

```
/skillgoid:synthesize-gates https://github.com/pallets/flask
/skillgoid:synthesize-gates ./my-reference-project ./another-reference
```

**What it does:**

1. Grounds observations against the analogue(s) and your `goal.md`.
2. Dispatches a synthesis subagent to propose gates with full provenance comments.
3. Validates proposed gates against `schemas/criteria.schema.json`.
4. Runs oracle validation — checks that each gate actually discriminates the analogue from an empty scaffold. Proposed gates get a `# validated: oracle | smoke-only | none` label.
5. Writes `.skillgoid/criteria.yaml.proposed` — never overwrites an existing `criteria.yaml`.

**Flags:**

| Flag | Effect |
|---|---|
| `--skip-validation` | Skip oracle validation (Stage 3). Useful when analogue deps aren't installed. |
| `--validate-only` | Re-run oracle validation on an existing `drafts.json` — no new synthesis. |

Review and rename `.skillgoid/criteria.yaml.proposed` → `criteria.yaml` when satisfied.

---

## Custom language adapters

Skillgoid ships with `python-gates`. To add Node.js, Go, Rust, or any other language:

1. Create `skills/<language>-gates/SKILL.md` implementing the gate adapter contract.
2. Optionally add `scripts/measure_<language>.py` (or equivalent) for non-trivial measurement logic.

**Adapter contract** — the skill receives project path + a filtered `criteria.yaml` subset and must emit to stdout:

```json
{
  "passed": true,
  "results": [
    {"gate_id": "lint", "passed": true, "stdout": "...", "stderr": "", "hint": ""}
  ]
}
```

Exit code: `0` all passed, `1` any failed, `2` internal error. Always emit valid JSON, even on partial failure.

See [docs/custom-adapter-template.md](docs/custom-adapter-template.md) for a full skeleton and the gate-type enumeration contract.

---

## Recovery

### Stalled chunk

When a chunk exits `stalled` (same failure repeated twice), the orchestrator surfaces a menu:

```
• /skillgoid:build resume              retry with same budget
• /skillgoid:unstick <id> "<hint>"     re-dispatch with a human hint
• /skillgoid:build retrospect-only     finalize as-is
```

`unstick` is capped at 3 invocations per chunk — after that, treat it as budget-exhausted and finalize or adjust `criteria.yaml`.

### Iteration file not written

If a chunk subagent returns without writing its iteration file, the orchestrator halts the wave before the gate check and reports the missing chunks. Fix options: re-dispatch via `resume`, or write the file by hand (JSON schema at `schemas/iterations.schema.json`).

### Stop hook blocks exit

The `Stop` hook fires when you try to end a Claude Code session mid-loop with failing gates and remaining budget. This is intentional — it surfaces the top-2 failing gate hints so you can decide whether to continue. To override, run `/skillgoid:build retrospect-only` first.

---

## Development

```bash
git clone https://github.com/metachungoid/skillgoid-plugin.git
cd skillgoid-plugin

# install dev deps
pip install -e ".[dev]"

# run tests
make test           # or: pytest

# run a single test
pytest tests/test_measure_python.py::test_name -v

# lint
make lint           # or: ruff check .

# install locally for manual testing
make install-local  # or: claude plugin install .
```

Python ≥ 3.11 required. Dev deps: `pytest`, `pyyaml`, `jsonschema`, `ruff`, `mypy`.

**Architecture notes:**

- **Skills are prose; scripts are code.** `skills/*/SKILL.md` are the procedural contracts. Non-trivial logic lives in `scripts/*.py` — the skill shells out. When adding behaviour, grow a script and reference it from the skill.
- **Tests assert prose contracts.** Behaviour that runs inside Agent-tool dispatches (build loop, retry logic, context7 fetcher) is not reachable from pytest. Tests in `tests/test_*_skill.py` assert that the SKILL.md files contain the required prose, which acts as the specification contract.
- **Backward compatibility.** Every release since v0.2 has been additive. Preserve that invariant when changing schemas, iteration file shapes, or skill inputs.

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

---

## License

MIT — see [LICENSE](LICENSE).
