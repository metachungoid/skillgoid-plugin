# Skillgoid v0.3 — Polish & Observe

- **Date:** 2026-04-17
- **Status:** Draft, pre-implementation
- **Supersedes:** nothing — extends v0.2
- **Scope:** Six additive improvements that sharpen what v0.2 already does. No architectural change.

---

## 1. Positioning

v0.3 is deliberately non-architectural. Nothing about how the build loop decomposes, dispatches, or terminates changes. We're tightening edges: better per-iteration data, safer gate execution, sharper user-facing messages, and the first cross-project metrics scaffolding.

Rationale: after shipping two back-to-back architectural bundles (v0 → v0.2), a polish release consolidates the surface before v0.4's adaptive-planning work. If real-world v0.2/v0.3 usage surfaces priorities we didn't predict, v0.4 re-ranks against observed ROI rather than predicted.

## 2. Non-goals

- Plan refinement mid-build (v0.4 material — architecturally risky, deserves its own spec)
- Unstick skill (v0.4 — pairs naturally with plan refinement)
- Pre-plan feasibility gate (v0.4 — cheap, but belongs with the judgment-layer work)
- Parallel chunks, polyglot, rehearsal mode (all v0.4+)
- Dashboards / metrics readers (v0.4+ after data accumulates)
- Gate-type plugins / more language adapters (ecosystem work, wait for demand)
- Tighter vault retrieval (v0.2's full-file read is fine at current vault sizes)

## 3. Six components

### 3.1 Diff-based reflection

Every `iterations/NNN.json` gains a `changes` field populated from the per-iteration git commit (which v0.2 already produces).

**Shape:**
```json
"changes": {
  "files_touched": ["src/auth.py", "tests/test_auth.py"],
  "net_lines": 34,
  "diff_summary": "auth.py: +12/-3, tests: +25/-0"
}
```

**Source:** `git diff --numstat HEAD~1..HEAD` captured at the end of the iteration's build step (after git commit). Parsed into the three fields above.

**Why it matters:**
- Stall analysis becomes sharper — identical `failure_signature` + identical-size `changes.net_lines` across two iterations is near-definitive thrashing.
- Retrospect gains a "what did each iteration actually change" view without diffing N commits by hand.
- Reflection prose can reference what was touched; lets Claude correlate "I changed X but pytest still fails on Y."

**Edge cases:**
- First iteration (no HEAD~1): `changes` field is written with `files_touched` = all files staged, `net_lines` = total lines in the diff against the empty tree.
- Non-git projects: skip the `changes` field entirely (no git-per-iteration means no diff to compute).
- `git diff --numstat` shows per-file numbers as `<added>\t<deleted>\t<path>` or `-\t-\t<path>` for binary files; binary files show as `(binary)` in `diff_summary`.

### 3.2 Adapter timeouts

Every gate item can carry an optional `timeout` (integer seconds).

**Schema change:** `criteria.schema.json` gate items gain an optional `timeout: {type: integer, minimum: 1, default: 300}` property (same for `integration_gates[]` items).

**Handler change:** `scripts/measure_python.py` — every `subprocess.run` call in a gate handler passes `timeout=gate.get("timeout", 300)`. On `subprocess.TimeoutExpired`, return:

```python
GateResult(
    gate["id"], False, "", "",
    f"gate timed out after {timeout}s — check for infinite loops or hung I/O",
)
```

**Scope:** applies to every gate type (`pytest`, `ruff`, `mypy`, `import-clean`, `cli-command-runs`, `run-command`, and the new `coverage` below).

**Why it matters:** a `while True:` in a user's test or a gate command that blocks on stdin today hangs the adapter indefinitely, burning budget and blocking the loop's budget-exhaustion exit. Timeouts make the failure mode fast and loud.

### 3.3 Better `gate-guard.sh` messages

The Stop hook currently blocks with: "gates still failing (pytest) and loop budget remains (2/5)." Useful but thin — user has to read iteration JSON to know *why* the gate failed.

**New message:** includes the top 1–2 failing gates' `hint` strings:

```
Skillgoid: gates still failing (pytest) and loop budget remains (2/5).
→ pytest hint: "2 tests failed in test_auth.py — likely missing session fixture"
→ ruff hint: "F401 unused import `os` in src/auth.py:1"
Continue with /skillgoid:build resume, or break with /skillgoid:build retrospect-only.
```

**Source:** `gate-guard.sh` already reads the latest iteration's `gate_report`. Extend to extract `hint` from each failing `results[]` entry, truncate each hint to 120 chars, include up to 2 (the two with longest hints — most informative).

**Why it matters:** when the Stop hook fires, the user often wants to know whether to let Claude keep going or break out and debug. The current message is too thin to decide; hints make the decision fast.

### 3.4 Model tiering via `criteria.yaml`

v0.2 hardcodes subagent models: `sonnet` for chunks, `haiku` for integration. Add optional per-project override:

**Schema change:** new top-level `models` object in `criteria.yaml`:

```yaml
models:
  chunk_subagent: sonnet          # default
  integration_subagent: haiku     # default
```

Both fields optional; any unspecified field uses the v0.2 default.

**Skill change:** `build` skill, when constructing Agent tool calls, reads `criteria.yaml → models` and substitutes the chosen model in the `model=` arg.

**Why it matters:** hard projects may want `opus` for chunk subagents; cheap throwaway projects may want `haiku` for chunk subagents. Pure measurement (integration) almost always stays on `haiku` but users can override.

### 3.5 Coverage gate type

Add `coverage` to the gate-type enum. New handler in `measure_python.py`.

**Schema change:** gate-type enum in `criteria.schema.json` extended to include `coverage`. New optional gate fields:
- `min_percent` (integer 0–100, default 80) — fail if coverage below this.
- `compare_to_baseline` (boolean, default false) — also fail if coverage dropped vs. the previous iteration's coverage gate result.

**Handler behavior:**
1. Run `python -m pytest --cov=. --cov-report=json` (pytest-cov is already in dev deps).
2. Parse `.coverage.json` (or whatever path pytest-cov writes to — `coverage.json` by convention).
3. Extract overall `totals.percent_covered`.
4. Fail if `< min_percent`; hint: "coverage {pct}% below floor {min_percent}%".
5. If `compare_to_baseline=true`: look for the previous iteration's coverage gate result (search `.skillgoid/iterations/` backwards by iteration number for a gate with the same `id`); if its `stdout` included a percent, fail when the new percent dropped more than 0.5pp. Hint: "coverage regressed from X% to Y%".

**Store the current percent in `stdout`** as a parseable string (e.g., `"coverage: 84.3%"`) so the next iteration's comparison has a stable source.

**Why it matters:** `pytest` gate passing is necessary but not sufficient — the tests may only cover code that already existed. A coverage gate catches the "my tests pass because the feature doesn't exist yet" trap without requiring anyone to write explicit test assertions for it.

### 3.6 Telemetry jsonl

Cross-project metrics accumulator at `~/.claude/skillgoid/metrics.jsonl`. Append-only. One line per finished project (successful OR abandoned).

**Line shape** (one JSON object per line):
```json
{
  "timestamp": "2026-04-17T15:42:00Z",
  "slug": "hello-cli",
  "language": "python",
  "outcome": "success",
  "chunks": 3,
  "total_iterations": 11,
  "stall_count": 0,
  "budget_exhausted_count": 0,
  "integration_retries_used": 0,
  "elapsed_seconds": 1837
}
```

**When written:** `retrospect` skill appends this line after writing `.skillgoid/retrospective.md`. The skill gathers the data from `.skillgoid/iterations/*.json` (count iterations, count `exit_reason == "stalled"` / `"budget_exhausted"`) and `.skillgoid/integration/*.json` (count attempts beyond the first).

**`elapsed_seconds`** is computed from the earliest `started_at` in iterations and the latest `ended_at`. If timestamps are missing (legacy project), write `elapsed_seconds: null`.

**What it enables:** nothing visible in v0.3 — it's scaffolding. v0.4 can build `/skillgoid:stats` or dashboards. The data accumulating from day one is the asset.

**Privacy:** the jsonl lives in the user's home directory, never phoned home. No external transmission.

## 4. Data-layout summary

### 4.1 `criteria.yaml` new fields

```yaml
# Existing in v0.2: language, loop, gates, integration_gates, integration_retries, acceptance

models:
  chunk_subagent: sonnet          # optional, default sonnet
  integration_subagent: haiku     # optional, default haiku

# Gate items gain optional `timeout`:
gates:
  - id: pytest
    type: pytest
    timeout: 600                  # optional, default 300

# New gate type `coverage`:
  - id: cov
    type: coverage
    min_percent: 80
    compare_to_baseline: true
```

### 4.2 `.skillgoid/iterations/NNN.json` new field

```json
{
  "...v0.2 fields...": "...",
  "changes": {
    "files_touched": ["path1", "path2"],
    "net_lines": 34,
    "diff_summary": "..."
  }
}
```

Optional — iterations from non-git projects skip it; v0.2 records without it still parse.

### 4.3 `~/.claude/skillgoid/metrics.jsonl` (new user-global file)

Append-only, one JSON object per line, one line per finished project. See §3.6 for shape.

## 5. Schema changes

- `criteria.schema.json`:
  - Gate items (both in `gates[]` and `integration_gates[]`) gain optional `timeout`.
  - Gate-type enum adds `"coverage"`.
  - New optional top-level `models` object with `chunk_subagent` and `integration_subagent` string fields.
- `iterations.schema.json`:
  - Add optional `changes` object with `files_touched: string[]`, `net_lines: integer`, `diff_summary: string`.

## 6. Skill changes

- `skills/loop/SKILL.md` — after git-commit step, compute `git diff --numstat HEAD~1..HEAD` and populate `changes` in iteration JSON.
- `skills/build/SKILL.md` — when constructing Agent tool calls, read `criteria.yaml → models` for overrides (fall back to v0.2 defaults).
- `skills/retrospect/SKILL.md` — append a summary line to `~/.claude/skillgoid/metrics.jsonl` after writing `retrospective.md`.
- `skills/clarify/SKILL.md` — for projects with a `pytest` gate and language=python, propose a default `coverage` gate (`min_percent: 80`, `compare_to_baseline: false` — regression checks are opt-in).
- `skills/python-gates/SKILL.md` — minor update noting that gates may carry a `timeout` field that the adapter honors. No structural change.

## 7. Hook changes

`hooks/gate-guard.sh`:
- Parse the latest iteration JSON (already does).
- Extract `hint` from each failing `results[]` entry.
- Sort failing gates by `len(hint)` descending; take top 2.
- Include in the block reason as `"→ <gate_id> hint: \"<hint-truncated-to-120-chars>\""` lines.

## 8. Testing strategy

- **Unit tests** for timeout handling — 2 tests: a gate that takes longer than its timeout fails with the expected hint; a gate that completes under timeout passes normally.
- **Unit tests** for coverage gate — 3 tests: passing project with coverage above floor passes; project with coverage below floor fails with hint mentioning the number; regression detection catches a drop (requires two mocked iteration files).
- **Schema tests** — 3 new tests: `timeout` field accepted; `coverage` gate type in enum; `models` block validates.
- **Skill prose tests** — none (skills are prose consumed by Claude at runtime).
- **Metrics jsonl test** — 1 test: given a `.skillgoid/iterations/` fixture, invoke the append helper (extracted as `scripts/metrics_append.py`) and verify the jsonl line shape.
- **Gate-guard message test** — 1 test: latest iteration with multiple failing gates + hints produces a block reason containing top-2 hints.

**Expected total:** 54 (v0.2) + 10 new = 64 tests.

## 9. Skill-level invocation diagram (v0.3)

No structural change from v0.2. Same dispatch pattern. v0.3 just enriches what flows through it.

```
user → /skillgoid:build "<goal>"
  │
  ├── retrieve → clarify (now proposes coverage gate) → plan
  ├── For each chunk: Agent(subagent_type, <model from criteria.models>) → loop
  │                                                        │
  │                                                        └── (adapter honors timeout;
  │                                                            iterations include changes;
  │                                                            coverage gate available)
  ├── Integration phase (model from criteria.models.integration_subagent)
  │
  └── retrospect → append metrics.jsonl line
```

## 10. Backward compatibility

Fully additive:
- Missing `models` → v0.2 hardcoded defaults apply.
- Missing `timeout` on a gate → default 300s.
- Missing `coverage` gate → not in project criteria, nothing changes.
- Missing `changes` in an iteration record → reader ignores it; schema allows it.
- Missing `metrics.jsonl` → retrospect creates on first write; v0.2 projects that never run v0.3 retrospect are unaffected.
- gate-guard.sh updated message works on v0.2-era iteration records (hints already exist in v0.2's GateResult shape).

No migration. v0.2 projects resume cleanly under v0.3.

## 11. Risks

All low — this is a polish release.

| Risk | Likelihood | Mitigation |
|---|---|---|
| `git diff --numstat` output parsing edge cases (binary files, renames) | Medium | Explicit handling for `-\t-\t` (binary) and `{old => new}` (rename). Fallback: if parse fails, write `changes: {files_touched: [], net_lines: 0, diff_summary: "diff parse failed"}`. |
| Coverage gate misconfigured (no pytest-cov installed in target project) | Low | Handler detects missing pytest-cov, returns failing GateResult with hint "pytest-cov not installed in project; add to dev dependencies". |
| `metrics.jsonl` grows unbounded | Low | Append-only is cheap; 1KB per project = 1MB after 1000 projects. Rotation is v0.4+ concern. |
| Timeout interacts badly with user's own pytest timeout plugins | Low | adapter's timeout is outermost; user's pytest-timeout inside it fires first. Well-behaved composition. |
| Model tiering misconfig (user specifies a nonexistent model) | Medium | `build` skill validates the model name against a known set (sonnet/haiku/opus and numeric variants) before Agent dispatch; falls back to default on unknown with a stderr warning. |

## 12. Open questions for the planning pass

1. **Metrics append helper — script vs inline.** Should the jsonl append logic live in `scripts/metrics_append.py` (unit-testable) or inline in `retrospect` skill prose (no new helper)? I'd lean script — easier to test, reusable if v0.4 adds a reader.
2. **Changes field for first iteration** — what does `net_lines` mean when there's no HEAD~1? Using `git diff --numstat HEAD` against empty tree gives a working answer but inflates the first iteration's net_lines. Acceptable, just document it.
3. **Coverage baseline storage** — store the baseline percent in iteration JSON (as parsed from `gate_report.results[].stdout`) vs. in a separate `.skillgoid/coverage-history.json`. Former is simpler; latter is more explicit. Start with former.
4. **Model tiering validation** — hardcoded list of valid model names vs. let Agent tool reject bad names at dispatch time. Hardcoded is safer but needs updating when Anthropic ships new models. Probably start hardcoded with a one-line comment about where to update.

## 13. Complexity budget

Estimated plan size: ~10 tasks.

- Diff-based reflection: 1 task (loop skill prose + helper + test)
- Adapter timeouts: 1 task (schema + measure_python.py handler extension + 2 tests)
- Coverage gate: 2 tasks (handler + baseline compare + schema + tests)
- Model tiering: 1 task (schema + build skill prose + validation test)
- Telemetry: 2 tasks (metrics_append helper + test + retrospect skill prose)
- Gate-guard messages: 1 task (bash hook update + test)
- Schema tests consolidation: 1 task
- Docs (README + CHANGELOG): 1 task

No new skills. No new directory structure. Everything slots into v0.2's layout.

## 14. Definition of done

v0.3 ships when:
- All v0.2 tests still pass (54).
- New tests pass (~10 new, ~64 total).
- Example smoke test (`examples/hello-cli`) now produces a `metrics.jsonl` entry on retrospect.
- `README.md` updated with "What's new in v0.3" section.
- `CHANGELOG.md` adds a `[0.3.0]` entry.
- Roadmap (`docs/roadmap.md`) updated to reflect what shipped and what remains for v0.4.
