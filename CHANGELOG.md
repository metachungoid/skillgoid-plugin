# Changelog

All notable changes to Skillgoid. Format: Keep a Changelog. Versioning: SemVer.

## [0.3.0] — 2026-04-17

### Added
- `scripts/diff_summary.py` — parses `git diff --numstat` into `{files_touched, net_lines, diff_summary}`.
- `scripts/metrics_append.py` — appends per-project stats to `~/.claude/skillgoid/metrics.jsonl` (local only, never transmitted).
- `coverage` gate type in `measure_python.py` — supports `min_percent` (default 80) and `compare_to_baseline` regression detection.
- Optional `timeout` field on every gate (default 300s). Converts `TimeoutExpired` to a failing GateResult with a clear hint.
- Optional `models:` block in `criteria.yaml` — override chunk/integration subagent model per-project.
- `changes` field on every iteration record (from `diff_summary.py`).

### Changed
- `hooks/gate-guard.sh` block reason now includes top-2 failing gate hints.
- `loop` skill procedure writes the `changes` field to each iteration record after the git-commit step.
- `build` skill reads `criteria.yaml → models` for Agent tool dispatch (falls back to v0.2 defaults).
- `clarify` skill proposes a default `coverage` gate for Python projects with `pytest`.
- `retrospect` skill appends a line to `~/.claude/skillgoid/metrics.jsonl` after writing the retrospective.
- `python-gates` skill documentation notes the timeout field is honored.

### Backward compatibility
- v0.2 `criteria.yaml` / iteration records parse unchanged.
- Missing `timeout` → default 300s.
- Missing `models` → v0.2 defaults (sonnet for chunk, haiku for integration).
- Missing `coverage` gate → no behavior change.
- Non-git projects skip the `changes` field entirely.

## [0.2.0] — 2026-04-17

### Added
- Subagent-per-chunk isolation: `build` skill now dispatches a fresh subagent per chunk via the `Agent` tool, bounding context and preventing cross-chunk interference.
- Deterministic stall detection via `scripts/stall_check.py` — 16-char hex signature from sorted failing gate IDs + first 200 chars of failing stderr.
- Git-per-iteration commits via `scripts/git_iter_commit.py` — structured `skillgoid:` messages with chunk id, iteration number, gate summary, signature. Noops on non-git projects.
- `integration_gates:` criteria field — optional end-to-end gates that run once after all per-chunk gates pass. Uses an integration subagent (Haiku, since it's pure measurement).
- Auto-repair on integration failure: identify suspect chunk via filename grep, re-dispatch that chunk's loop subagent with failure context, re-run integration. Up to `integration_retries` (default 2) attempts.
- `loop.skip_git` config option to opt out of git-per-iteration.
- `schemas/iterations.schema.json` — locks the iteration JSON shape including `failure_signature` (16-hex regex) and `exit_reason` enum.
- `clarify` skill now proposes a sensible default `integration_gates` entry by project type (CLI / library / service).
- `plan` skill now requires per-module blueprint headings that map 1:1 to chunk ids (forward-compat for v0.3 blueprint slicing).

### Changed
- `loop` skill procedure — step 8 now writes `failure_signature` via `stall_check.py`; new step 8.1 runs `git_iter_commit.py`; stall exit condition is signature equality, not judgment.
- `build` skill — rewritten as a pure orchestrator/dispatcher. No longer invokes `skillgoid:loop` inline.

### Backward compatibility
- v0 `criteria.yaml` / `chunks.yaml` / iteration records all parse unchanged.
- Projects not in git are unaffected (git-per-iteration is a noop).
- `integration_gates` is optional — v0 projects skip the phase entirely.

## [0.1.0] — 2026-04-17

Initial v0 release. See `docs/superpowers/specs/2026-04-17-skillgoid-design.md` for the concept.
