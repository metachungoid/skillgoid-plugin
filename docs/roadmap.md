# Skillgoid roadmap

## Shipped

### v0 (2026-04-17)
The concept: criteria-gated build loop + compounding per-language vault.
Spec: `docs/superpowers/specs/2026-04-17-skillgoid-design.md`
Plan: `docs/superpowers/plans/2026-04-17-skillgoid-v0.md`

### v0.2 — Production Hardening Bundle (2026-04-17)
Three structural upgrades so the criteria-gated loop survives multi-chunk projects:
- Subagent-per-chunk isolation
- Deterministic stall detection + git-per-iteration
- Integration gate after all chunks
Spec: `docs/superpowers/specs/2026-04-17-skillgoid-v0.2-production-hardening.md`
Plan: `docs/superpowers/plans/2026-04-17-skillgoid-v0.2.md`

### v0.3 — Polish & Observe (2026-04-17)
Six additive polish items, zero architectural change:
- Adapter timeouts per gate (default 300s)
- Coverage gate type (min_percent + compare_to_baseline)
- Diff-based reflection (`changes` field per iteration)
- Better `gate-guard` messages (surface top-2 failing gate hints)
- Model tiering via `criteria.yaml → models`
- Cross-project metrics jsonl scaffolding
Spec: `docs/superpowers/specs/2026-04-17-skillgoid-v0.3-polish-observe.md`
Plan: `docs/superpowers/plans/2026-04-17-skillgoid-v0.3.md`

### v0.4 — Integration Polish & Unstick (2026-04-18)
Observed-ROI reprioritization driven by the first real run (jyctl):
- Gate `env:` field + python binary auto-resolution
- Pre-plan feasibility skill (catches env mismatches before iter 1)
- Unstick skill (one-sentence hint → chunk re-dispatch)
- `/skillgoid:stats` reader for metrics.jsonl
- Clarify: default `.gitignore` + subprocess-coverage caveat
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.4-integration-polish-and-unstick.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.4.md`

### v0.5 — Evidence-Driven Polish (2026-04-18)
Small ship based on 3-real-run evidence:
- Parallel chunks (wave-based dispatch) — observed on mdstats (parser + counters independent)
- Vault supersession tracking — addresses stale lessons from jyctl era
- Feasibility scaffolding awareness — fixes false positive on fresh projects
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.5-evidence-driven-polish.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.5.md`

### v0.6 — Shell-String Python Resolution (2026-04-18)
One-item micro-release driven by indexgrep evidence:
- `SKILLGOID_PYTHON` env export covers `bash -c` / `sh -c` style gates where v0.4's auto-resolution can't reach.
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.6-shell-python.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.6.md`

### v0.7 — Correctness Bundle (2026-04-18)
Two items driven by the `taskbridge` polyglot stress run:
- Gate `env:` honored by every gate type (pytest, import-clean, coverage, ruff, mypy — previously hardcoded)
- Parallel-wave safety: per-chunk iteration filenames + `paths:`-scoped commits (kills the filename race + git-add-A cross-contamination observed in v0.5's parallel feature)
- Folded in: `git_iter_commit.py --iteration` path resolution (F25); coverage → integration_gates by default in clarify
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.7-correctness-bundle.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.7.md`

### v0.8 — Correctness + Subagent Discipline Bundle (2026-04-18)
Five items covering 7 findings from the minischeme 18-chunk stress run:
- Iteration JSON schema validation before commit (F5, F9)
- `chunk_topo` auto-serializes same-file chunks in parallel waves (F8)
- `chunks.yaml` gains optional `gate_overrides:` for per-chunk gate arg narrowing (F3, F12)
- Blueprint slicing via `scripts/blueprint_slice.py` — finally, after being deferred since v0.2 (F7)
- `## Cross-chunk types` blueprint convention (F6)
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.8-correctness-and-discipline.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.8.md`

## Formally closed (sufficient evidence)

- **Plan refinement mid-build.** Zero evidence across 8 real runs: jyctl, taskq, mdstats, indexgrep, findings, taskbridge (polyglot), minischeme (18-chunk stress), plus the v0.6 ship-less decision point. The minischeme run was the canonical case where plan refinement "should" have been needed — compiler-style project with mid-build IR-shape discovery — and it wasn't. Not reopening without qualitatively new evidence.

## Dropped from roadmap (v0.6 decision)

- **Plan refinement mid-build.** Four real runs, zero evidence. Formally dropped. Re-evaluation would require qualitatively different project shapes (research-grade builds with genuine decomposition uncertainty) AND two+ subsequent runs still producing evidence for the need. (Superseded by the "Formally closed" entry above as of v0.8.)

## Deferred — await qualitatively different project shapes

Items kept deferred because no real run has exercised them. Don't revive without new evidence.

- **Polyglot / multi-language projects.** All 4 real runs have been single-language python. Until a project actually demands it, don't build.
- **Parallel chunks extensions.** v0.5 shipped the core — indexgrep validated a 3-way parallel wave. No further parallel-chunks work until a run surfaces an unmet need (e.g., failures when waves exceed some N, or a need for parallel-subagent retry coordination).
- **Rehearsal mode.** Subsumed by v0.4 feasibility + v0.5 scaffolding awareness.
- **More language adapters** (`node-gates`, `go-gates`, `rust-gates`). Wait for a project that demands them.
- **Gate-type plugins.** Premature abstraction; no ecosystem demand.
- **Dashboards / HTML rendering.** `/skillgoid:stats` markdown sufficient.
- **Tighter vault retrieval.** 5 entries after 4 projects; no scale pressure.

## How to pick up v0.9

Currently deferred v0.8+ items:
- **Polyglot language support** (`languages[]` migration, polyglot clarify defaults, node-gates adapter, multi-language vault/metrics). Waits on 2-3 ORGANIC polyglot runs. `taskbridge` was synthetic; doesn't count. If and when real polyglot-user projects surface, design v0.9 around their shape.
- **F10 (out-of-pipeline commits by subagents fixing adjacent chunks' tests):** one observation in minischeme. Needs 2+ more to justify machinery. Document the pattern but don't formalize yet.
- **F11 (double-commit symptom):** v0.8 schema validation should incidentally address it. If it recurs post-v0.8, investigate separately.
- **Glob-aware paths overlap detection:** v0.8 uses exact-string match. If a user project shows overlapping globs the exact matcher misses, add glob-aware matching in v0.9.
- **Per-chunk blueprint files (alternative to in-memory slicing):** v0.8 went with in-memory. If users want on-disk per-chunk blueprints for audit, revisit.
- **Rehearsal mode, gate-type plugins, dashboards:** unchanged from v0.7's deferred list — no new evidence.

Historical v0.8 intake guidance (now shipped — the minischeme run produced the v0.8 evidence):

Additional for v0.8 (driven by taskbridge findings deferred from v0.7):
- Polyglot language-support shape (`languages[]` migration, polyglot clarify defaults, node-gates adapter) waits on 2-3 more polyglot project runs before committing to a design. One polyglot run exposed the correctness issues v0.7 ships; it is not enough evidence to commit to a full polyglot architecture.
- Other deferred from v0.7 findings doc: structured hint parity for `run-command` gates (F27), feasibility-phase awareness of Node tooling (F12), multi-language vault/metrics (F7+F1+F20+F21), `metrics_append` recording per-chunk languages (F20).

Original v0.7 intake guidance (now historical — the taskbridge run produced the v0.7 evidence):

1. Run Skillgoid on a **qualitatively different** project shape (not another python CLI). Real candidates:
   - A polyglot project (Python backend + Node CLI wrapper) — would need `node-gates` adapter first.
   - An async/concurrent project — may surface timeout-during-async-io issues.
   - A project with **genuine planning uncertainty** (e.g., "design a system that processes X" where the decomposition isn't obvious upfront) — the only real test of plan-refinement value.
2. Observe what actually fails. Demote predicted-ROI items that don't surface.
3. Spec v0.7 around the top 1-2 observed issues.
4. **Shipping less is the correct response to real-world data** — v0.2 shipped 3 big items, v0.3 shipped 6 polish items, v0.4 shipped 4 items, v0.5 shipped 3, v0.6 shipped 1. The trajectory is correct.
