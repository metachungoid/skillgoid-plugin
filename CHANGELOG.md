# Changelog

All notable changes to Skillgoid. Format: Keep a Changelog. Versioning: SemVer.

## [0.8.0] — 2026-04-18

### Changed
- `scripts/git_iter_commit.py` now validates iteration JSON against `schemas/iterations.schema.json` before acquiring the commit lock. Records missing required fields (e.g., `gate_report`) or with wrong types (e.g., `iteration: "001"` as string) are refused with exit 2 and a clear error pointing at the bad field.
- `scripts/chunk_topo.py` `plan_waves()` now auto-serializes chunks in the same wave whose `paths:` overlap. When overlap is detected, the wave is split into consecutive sub-waves (alphabetical by `chunk_id` for determinism). Prevents the same-file-same-wave commit cross-contamination observed in the minischeme stress run where `tail-calls` and `error-handling` both modified `evaluator.py`.
- `skills/build/SKILL.md` subagent prompt construction now invokes `scripts/blueprint_slice.py` and passes only the chunk's section + `## Architecture overview` + `## Cross-chunk types` (when present) to each subagent. Replaces v0.2's "passes whole file" punt.
- `skills/loop/SKILL.md` step 3.1 applies `chunk.gate_overrides` when filtering the criteria subset for measurement.
- `skills/plan/SKILL.md` instructs blueprint authors to include a `## Cross-chunk types` section, propose `gate_overrides` per chunk, and avoid same-file chunks in the same wave.

### Added
- `scripts/validate_iteration.py` — iteration JSON schema validator (importable + CLI).
- `scripts/blueprint_slice.py` — chunk-aware blueprint slicer (importable + CLI).
- `chunks.yaml` schema gains optional `gate_overrides:` field per chunk.
- New `tests/test_validate_iteration.py`, `tests/test_blueprint_slice.py`, `tests/test_gate_overrides.py`, `tests/test_v08_bundle.py`. Plus +5 tests to `test_chunk_topo.py`, +3 to `test_schemas.py`, +2 to `test_git_iter_commit.py`. Total new tests: ~35.

### Formally closed (sufficient evidence)
- **Plan refinement mid-build.** Zero evidence across 8 real runs (including the 18-chunk minischeme stress run — canonical case for mid-build IR-shape discovery, did not trigger the need). Roadmap updated to move this from "Deferred" to "Formally closed."

### Backward compatibility
- Existing `criteria.yaml`: unchanged behavior.
- Existing `chunks.yaml` without `gate_overrides`: unchanged.
- Existing `chunks.yaml` without `paths:` or with non-overlapping paths: `chunk_topo` behaves identically to v0.7.
- Existing `blueprint.md` without `## Cross-chunk types`: slicer warns but proceeds.
- Existing `blueprint.md` without `## <chunk_id>` H2 headings (legacy pre-v0.2 projects): slicer falls back to full-blueprint return with warning.
- Existing iteration JSONs that were always schema-valid: continue to pass. Records that were silently-schema-non-conforming (rare; observed once in minischeme stress run's `error-handling-001.json`) will now fail on resume — the migration path is to fix the bad record and re-run.

## [0.7.0] — 2026-04-18

### Changed
- Gate `env:` field is now honored by every gate type (previously only `run-command` and `cli-command-runs`). Backward-compatible: the default `<project>/src` PYTHONPATH injection for pytest/import-clean/coverage is preserved when gate `env:` doesn't specify PYTHONPATH.
- Iteration files are now named `<chunk_id>-NNN.json` (previously `NNN.json`). Readers handle both conventions for back-compat.
- `scripts/git_iter_commit.py` now accepts `--chunks-file` and uses each chunk's `paths:` field (new, optional in `chunks.yaml`) to stage only the chunk's own files. Falls back to `git add -A` with a stderr warning when `paths:` is absent.
- `scripts/git_iter_commit.py` now resolves a relative `--iteration` path against `--project` (previously required cwd to match project root).
- `scripts/git_iter_commit.py` now hard-fails (exit 2) on unreadable iteration JSON, and exits 1 when a git operation fails (previously silently soft-failed in both cases, hiding missed commits).
- `clarify` skill proposes `coverage` under `integration_gates:` by default, not inside per-chunk `gate_ids` (avoids false-positive failures from cross-chunk scope).
- `scripts/measure_python.py` `_gate_coverage` writes its scratch file to `tempfile.gettempdir()` instead of the project dir.

### Added
- Optional `paths:` field in `chunks.yaml` schema.
- 17 new tests covering env-in-every-handler, scoped git add, parallel-wave disjointness, mixed iteration-filename back-compat.

### Backward compatibility
- Existing `criteria.yaml`: unchanged behavior. Opt into broader env-support by adding `env:` to any gate.
- Existing `chunks.yaml`: unchanged behavior. Opt into scoped commits by adding `paths:` to chunks.
- Mixed-filename iteration dirs (v0.6 `NNN.json` + v0.7 `<chunk_id>-NNN.json`) are readable by all consumers.

## [0.6.0] — 2026-04-18

### Added
- `SKILLGOID_PYTHON` env var (value: `sys.executable`) is now exported to every gate subprocess by `_merge_env`. Shell command strings can reference `$SKILLGOID_PYTHON` to get a guaranteed-working python path — addresses the gap where v0.4's auto-resolution only covers `command[0]`, not substrings in shell bodies.

### Changed
- `python-gates` skill documents the `SKILLGOID_PYTHON` pattern.
- `clarify` skill proposes `$SKILLGOID_PYTHON` instead of bare `python` for service-style shell-pipeline integration gates.

### Backward compatibility
- Fully additive. v0.5 criteria/chunks/iterations parse unchanged.
- User gate env: can override SKILLGOID_PYTHON for niche cases (testing against a different interpreter).

### Removed from roadmap
- **Plan refinement mid-build.** Four real Skillgoid runs (jyctl, taskq, mdstats, indexgrep) at 3, 4, 6, and 7 chunks all produced zero evidence the feature is needed. Formally dropped from the roadmap as of v0.6. A v0.7+ re-evaluation would require qualitatively different project shapes (research-grade builds with genuine decomposition uncertainty) first.

## [0.5.0] — 2026-04-18

### Added
- `scripts/chunk_topo.py` — topological wave planner for parallel chunk dispatch.
- `scripts/vault_filter.py` — filter vault lessons by `Status: resolved in vX.Y`.

### Changed
- `build` skill now dispatches chunks in waves (parallel within each wave). Sequential projects unchanged; projects with independent chunks run concurrently.
- `feasibility` skill downgrades missing-relative-path-inside-project to a warning.
- `retrieve` skill filters vault lessons against the current plugin version before surfacing.
- Vault lesson format gains an optional `Status: resolved in vX.Y` line.

### Backward compatibility
- v0.4 `criteria.yaml` / `chunks.yaml` / vault files parse unchanged.
- Sequential chunks behave identically to v0.4 (single-chunk waves).
- Vault files without `Status:` lines surface as current advice (same as v0.4).

### Notably NOT included
- Plan refinement mid-build (3 real runs produced 0 evidence it's needed).
- Rehearsal mode (overlaps with v0.4 feasibility).
- Polyglot / more language adapters / gate-type plugins / dashboards (no demand signal).

## [0.4.0] — 2026-04-18

### Added
- `scripts/stats_reader.py` — metrics.jsonl summarizer helper.
- Optional `env:` dict on every gate (merged into subprocess env, path values resolved against project dir).
- Python binary auto-resolution: bare `python` in gate commands → `sys.executable`. Opt-out via `SKILLGOID_PYTHON_NO_RESOLVE=1`.
- New skills: `feasibility` (pre-plan gate check), `unstick` (stalled-chunk recovery with hint), `stats` (metrics summary).

### Changed
- `build` skill wires `feasibility` between `clarify` and `plan`; surfaces `/skillgoid:unstick` on chunk stall/budget-exhaustion.
- `clarify` skill proposes default `.gitignore` + subprocess-coverage caveat comment on coverage gates.
- `python-gates` skill documents `env:` field.

### Backward compatibility
- v0.3 `criteria.yaml` / iteration records parse unchanged.
- Missing `env:` → no env override, v0.3 behavior.
- Missing `feasibility` / `unstick` / `stats` skills → never-invoked-implicitly except feasibility (but if the skill is absent, build falls back to direct clarify→plan).

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
