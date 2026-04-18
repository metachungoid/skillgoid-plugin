# Skillgoid v0.5 — Evidence-Driven Polish

- **Date:** 2026-04-18
- **Status:** Draft, pre-implementation
- **Supersedes:** nothing — extends v0.4
- **Scope:** Three observed-ROI improvements, small bundle. Explicitly NOT including plan-refinement-mid-build (3 real runs produced zero evidence it's needed).

---

## 1. Why this is smaller than v0.2–v0.4

After v0.4 shipped, three real Skillgoid runs accumulated in `~/.claude/skillgoid/metrics.jsonl` — jyctl (3 chunks), taskq (4 chunks), and mdstats (6 chunks). The roadmap's original v0.5 plan centered on "plan refinement mid-build" (the predicted highest-value adaptive item). **Three real runs produced zero evidence that bet is correct:** every plan held end-to-end across all three projects. No chunk surfaced evidence that downstream decomposition was wrong.

What the real runs DID surface:

| Item | Evidence |
|---|---|
| Vault lessons become stale | Two vault entries ("python not on PATH", "cli-command-runs can't pass PYTHONPATH") were resolved by v0.4 but still surface as current advice. Misleading to v0.4 users. |
| Feasibility false positive on fresh projects | `PYTHONPATH: src` flagged failing because `src/` doesn't exist yet — but the scaffold chunk creates it. Happened on taskq + mdstats. |
| Genuinely parallelizable chunks | mdstats had one pair (parser + counters) that depend only on scaffold. Real wall-clock opportunity for bigger projects. |

What the real runs did NOT surface (despite being predicted-high items):

| Item | Evidence count after 3 runs |
|---|---|
| Plan refinement mid-build | 0 |
| Rehearsal mode needs | 0 |
| Unstick invocations | 0 stalls → 0 unstick uses |
| Polyglot need | 0 (all 3 projects single-language) |
| Dashboard need | 3 jsonl lines — markdown summary works fine |
| Tighter vault retrieval need | Vault has 1 file, 5 entries — no scale pressure |

**The v0.4 roadmap's speculative adaptive-bundle (plan refinement + rehearsal) is postponed until a real run demonstrates the need.** v0.5 ships what evidence supports: supersession tracking, feasibility polish, parallelism for chunks that are actually independent.

## 2. Non-goals (re-deferred to v0.6+)

- **Plan refinement mid-build** — 0/3 runs showed evidence. Revisit only after a real run demonstrates the need (e.g., a chunk whose iterations reveal the downstream decomposition is wrong).
- **Rehearsal mode** — overlaps with v0.4's feasibility; v0.5's feasibility polish addresses the one observed failure mode.
- **Polyglot / multi-language** — no demand across 3 runs.
- **Dashboards / HTML rendering** — `/skillgoid:stats` markdown sufficient at current scale.
- **Tighter vault retrieval** — no scale pressure (1 file, 5 entries after 3 projects).
- **More language adapters, gate-type plugins** — ecosystem work, no demand signal.

## 3. Core components

### 3.1 Vault supersession tracking

Vault lesson files (`~/.claude/skillgoid/vault/<language>-lessons.md`) gain an optional per-lesson `Status:` line that marks a lesson as resolved in a specific Skillgoid release. The `retrieve` skill reads the current plugin version from `.claude-plugin/plugin.json` and suppresses (or annotates) lessons whose `Status: resolved in vX.Y` is ≤ current version.

**Lesson format change (additive):**

```markdown
## `python` is not always on PATH

In environments that ship only `python3`, a `cli-command-runs` gate with `command: ["python", "-m", ...]` will fail with `FileNotFoundError`.

**Fix:** (v0.4+ auto-resolves this — see Status.)

Status: resolved in v0.4
Last touched: 2026-04-18 by project "taskq"
```

When the lesson file is next read by `retrieve`:
- If current Skillgoid version ≥ resolved version → the lesson is skipped (or rendered under a collapsed "Resolved by newer Skillgoid versions" section).
- If current version < resolved version (running an old plugin) → the lesson still surfaces as current advice.

**Why it matters:** the vault currently tells v0.4 users to work around v0.3-era bugs v0.4 already fixed. Over time, vault staleness compounds — retrieve becomes actively misleading, not just noisy.

**No schema change** required (vault files are prose). Changes live in `retrieve` skill prose + a lightweight `scripts/vault_filter.py` helper.

### 3.2 Feasibility scaffolding awareness

The `feasibility` skill currently fails a gate when `PYTHONPATH: src` is declared but `src/` doesn't exist in the project. On fresh projects, this is always a false positive — scaffold (chunk 1) creates `src/`. Observed on taskq and mdstats.

**Fix:** when the missing path is **inside the project dir** (relative path), downgrade to a warning with the note: "this path may be created by the scaffold chunk; will verify after chunk 1 runs." When the path is **absolute and outside project** (rare but possible), keep it as a failure.

**No new code required** — this is a prose update to `skills/feasibility/SKILL.md`'s procedure step 3 (the "check PATH-like values" step).

### 3.3 Parallel chunks

The `build` skill currently runs chunks sequentially. Real evidence (mdstats: parser and counters both depend only on scaffold) shows independent chunks exist in practice. Combined with v0.2's integration gate (which catches any cross-chunk interference), parallel dispatch is safe.

**Design:**

1. After `plan` writes `chunks.yaml`, compute execution "waves" via topological sort on `depends_on`:
   - Wave 0: chunks with no depends_on.
   - Wave N: chunks whose every dependency is in a prior wave.
2. For each wave, dispatch all chunks' subagents **concurrently** via parallel `Agent()` calls. Wait for every subagent in the wave to return before proceeding.
3. If any chunk in a wave exits `stalled` or `budget_exhausted`, let the siblings finish, then STOP — same rule as v0.4 (don't dispatch subsequent waves). Surface all failures to the user.
4. When all chunks succeed, run integration gates as before.

**Helper:** new `scripts/chunk_topo.py` exposes `plan_waves(chunks: list[dict]) -> list[list[str]]`. Raises on cycles or unresolvable `depends_on` refs.

**Tests:** unit tests for the topo-sort covering:
- Linear chain → N waves of 1 each.
- Parallel pair → fewer waves than chunks.
- mdstats-like (1 + 2 + 1 + 1 + 1 = 6 chunks in 5 waves).
- Missing dependency ref → raises.
- Cycle → raises.

**Why this is the largest v0.5 item:** meaningful architectural change to `build` skill prose (dispatch pattern) + a new helper + tests. Still small compared to v0.2's subagent isolation. Backward-compatible: a project with purely sequential chunks (jyctl, taskq) still gets one-chunk-per-wave, identical to v0.4 behavior.

## 4. Data-layout changes

### 4.1 Vault lesson files

New optional `Status: resolved in vX.Y` line per lesson. Additive — existing vault files parse unchanged. Absence of `Status:` means "still current."

### 4.2 No schema changes

`criteria.yaml`, `chunks.yaml`, `iterations/*.json` all unchanged. v0.4 projects resume under v0.5 cleanly.

### 4.3 `chunks.yaml` interpretation

No schema change — `depends_on` field was already present since v0. What changes is how `build` **uses** it: v0.4 used it as a strict sequencer ("don't dispatch chunk X until Y succeeded"); v0.5 uses it as a DAG for parallel scheduling.

## 5. Skill changes

- `skills/build/SKILL.md` — modest prose update in step 3. Replace "For each chunk in `chunks.yaml` in order" with "For each wave from `chunk_topo.plan_waves()`, dispatch every chunk in the wave concurrently."
- `skills/feasibility/SKILL.md` — procedure step 3 softens missing-project-relative-path check to a warning.
- `skills/retrieve/SKILL.md` — procedure step 2 reads current plugin version and filters lessons by `Status:`. Prose-only update; the `scripts/vault_filter.py` helper (if introduced) is optional.
- `skills/clarify/SKILL.md`, `skills/plan/SKILL.md`, `skills/retrospect/SKILL.md`, `skills/loop/SKILL.md`, `skills/python-gates/SKILL.md`, `skills/unstick/SKILL.md`, `skills/stats/SKILL.md` — **all unchanged.**

## 6. Hooks

No changes.

## 7. Testing strategy

- **`chunk_topo.plan_waves` unit tests** — 6 tests: linear chain, parallel pair, missing dep, cycle, mdstats-like mixed, empty input.
- **Vault-filter helper tests (optional)** — 3–4 tests if we extract a helper: filter removes resolved-in-older lessons, keeps current, parses missing Status field as "current", handles malformed Status lines gracefully.
- **No new schema tests** — schemas unchanged.
- **No runtime tests** for the parallel dispatch itself — that's Claude Code's `Agent` tool's responsibility. The topo helper is the testable unit.

**Expected test count:** 94 (v0.4) + ~10 new = ~104.

## 8. Backward compatibility

- Vault files without `Status:` lines work as before (lessons surface as current).
- Vault files with `Status:` lines are readable by v0.4's retrieve skill (v0.4 ignores unknown prose lines). No vault migration needed.
- chunks.yaml unchanged — v0.4 projects resume under v0.5; sequential chunks just dispatch as single-chunk waves.
- feasibility skill's softened check: v0.4 users who manually invoke feasibility will see warnings instead of errors on fresh projects — strictly looser, never stricter.

No migration required. v0.4 projects under v0.5 Just Work.

## 9. Complexity budget

Estimated plan size: ~8 tasks.

- Branch setup: 1 task (housekeeping, no code).
- `chunk_topo.py` + tests: 1 task.
- `build` skill prose update (wave dispatch): 1 task.
- `feasibility` skill prose update (scaffolding awareness): 1 task.
- `retrieve` skill prose update (vault filtering) + optional `vault_filter.py` helper + tests: 1-2 tasks.
- Vault file format update (annotate 2 existing jyctl lessons as "resolved in v0.4"): 1 task — part of the retrieve update or separate.
- Docs (README + CHANGELOG + roadmap): 1 task.

## 10. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Parallel chunks introduce race conditions on shared files (e.g., `iterations/NNN.json` numbering) | Medium | Each chunk writes with `chunk_id` in record; iteration N is per-chunk, not global. Subagents write their own files in their own chunk_id namespace. No collision. |
| Wave dispatch complicates auto-repair in integration gate (which chunk to re-dispatch if wave 3 of 5 passes but wave 4 has the suspect?) | Low | Auto-repair's suspect-chunk heuristic (filename grep from v0.2) is chunk-oriented, not wave-oriented. Continues to work. |
| Vault filter hides lessons a user wants to see | Low | The filter shows lessons under a collapsed "resolved in older versions" section, not deletes them. User can still see them on demand. |
| Feasibility softening misses a real misconfiguration | Low | Warning still surfaces to user; they can still abort. Only downgrade is severity, not visibility. |
| chunk_topo cycle detection wrong | Low | Clear unit tests; raise a named exception with cycle-member IDs. |

## 11. Open questions (for planning pass)

1. **Vault filter — helper script or inline in retrieve skill?** Leaning helper script for testability. Minor.
2. **How to read current plugin version?** Read `.claude-plugin/plugin.json` at retrieve time. Handle missing/malformed file by treating all lessons as current (fail-open on version detection).
3. **Does `plan` skill need any update to encourage identifying independent chunks?** Probably yes — one-line prose nudge that when two chunks both depend on scaffold and nothing else, they can be parallelized by v0.5. But not required for correctness.
4. **Should `/skillgoid:stats` gain a "parallel-chunks-utilized" metric?** Future nice-to-have. Not in v0.5.

## 12. Definition of done

- All v0.4 tests still pass (94).
- New tests pass (~10).
- `chunk_topo.plan_waves` correctly identifies mdstats's 5 waves from its 6 chunks.
- `retrieve` skill's prose describes version-based vault filtering.
- Vault file has two entries annotated with `Status: resolved in v0.4` (the PATH + PYTHONPATH lessons).
- README gets "What's new in v0.5" section; CHANGELOG adds `[0.5.0]`; roadmap moves v0.5 to Shipped, defines v0.6 (plan-refinement reclassified as "re-evaluate after more runs", polyglot stays deferred, etc.).
