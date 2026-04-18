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

## Dropped from roadmap (v0.6 decision)

- **Plan refinement mid-build.** Four real runs, zero evidence. Formally dropped. Re-evaluation would require qualitatively different project shapes (research-grade builds with genuine decomposition uncertainty) AND two+ subsequent runs still producing evidence for the need.

## Deferred — await qualitatively different project shapes

Items kept deferred because no real run has exercised them. Don't revive without new evidence.

- **Polyglot / multi-language projects.** All 4 real runs have been single-language python. Until a project actually demands it, don't build.
- **Parallel chunks extensions.** v0.5 shipped the core — indexgrep validated a 3-way parallel wave. No further parallel-chunks work until a run surfaces an unmet need (e.g., failures when waves exceed some N, or a need for parallel-subagent retry coordination).
- **Rehearsal mode.** Subsumed by v0.4 feasibility + v0.5 scaffolding awareness.
- **More language adapters** (`node-gates`, `go-gates`, `rust-gates`). Wait for a project that demands them.
- **Gate-type plugins.** Premature abstraction; no ecosystem demand.
- **Dashboards / HTML rendering.** `/skillgoid:stats` markdown sufficient.
- **Tighter vault retrieval.** 5 entries after 4 projects; no scale pressure.

## How to pick up v0.7

1. Run Skillgoid on a **qualitatively different** project shape (not another python CLI). Real candidates:
   - A polyglot project (Python backend + Node CLI wrapper) — would need `node-gates` adapter first.
   - An async/concurrent project — may surface timeout-during-async-io issues.
   - A project with **genuine planning uncertainty** (e.g., "design a system that processes X" where the decomposition isn't obvious upfront) — the only real test of plan-refinement value.
2. Observe what actually fails. Demote predicted-ROI items that don't surface.
3. Spec v0.7 around the top 1-2 observed issues.
4. **Shipping less is the correct response to real-world data** — v0.2 shipped 3 big items, v0.3 shipped 6 polish items, v0.4 shipped 4 items, v0.5 shipped 3, v0.6 shipped 1. The trajectory is correct.
