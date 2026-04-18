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

## Deferred — v0.6 goals

**Re-ranked by observed ROI.** Items that had zero evidence across 3 real runs are demoted; items that surfaced from actual failures are promoted.

### Demoted (kept deferred — no evidence after 3 real runs)

- **Plan refinement mid-build.** 0/3 runs demonstrated the need. Originally the highest-predicted-ROI item but consistently unvalidated. Don't ship on speculation. Revisit ONLY when a real run has a chunk whose iterations reveal downstream decomposition is wrong.
- **Rehearsal mode.** Subsumed by v0.4's feasibility + v0.5's scaffolding awareness.
- **Polyglot / multi-language.** No demand across 3 python projects.
- **Dashboards / HTML.** `/skillgoid:stats` markdown remains sufficient.
- **Tighter vault retrieval.** Vault has 5 entries — not a scale problem yet.
- **More language adapters.** No demand.
- **Gate-type plugins.** Premature abstraction.

### Possible v0.6 — when evidence demands

1. **Run Skillgoid on a STRUCTURALLY DIFFERENT project** (not another python CLI). Candidates: a small web service, a library with strict typing, a background worker with async I/O. Need shapes that stress different axes.
2. **Bigger vault query** — if `/skillgoid:stats` shows recurring stall signatures, a v0.6 feature could pre-emptively surface the matching vault lesson mid-build.
3. **Unstick actually invoked** — if a real run stalls and the user uses `/skillgoid:unstick`, evaluate whether its UX is good or needs v0.6 tweaks.

## How to pick up v0.6

1. Run `/skillgoid:stats` after v0.5 has been used on 3+ more real projects.
2. Look for recurring failure signatures — those are the real v0.6 priorities.
3. Don't revive v0.5's demoted items without new evidence.
