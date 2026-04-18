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

## Deferred — v0.4 goals

After v0.2 and v0.3 have been used on at least one real project, re-rank these by observed ROI.

### Adaptive / judgment upgrades (highest expected value)

- **Plan refinement mid-build.** After chunk N passes, if its iterations surfaced evidence that downstream chunks are miscalibrated, `build` re-invokes `plan` with the new evidence. Currently v0.2/v0.3 surface to user.
- **Pre-plan feasibility gate.** After `clarify`, a quick adversarial pass before committing to the plan.
- **Unstick skill.** `/skillgoid:unstick <chunk> "<hint>"` re-dispatches a stalled chunk with the hint injected.
- **Rehearsal mode.** Dry-run each chunk's first iteration before committing chunks.yaml.

### Scale / throughput upgrades

- **Parallel chunks** (now safer with v0.2's integration gate catching interference).
- **Polyglot / multi-language projects** — per-chunk adapter + vault across languages.

### Observability readers (v0.3's scaffolding becomes useful)

- `/skillgoid:stats` — reads `~/.claude/skillgoid/metrics.jsonl` and summarizes.
- Optional markdown/HTML dashboards.

### Quality / safety upgrades

- **Tighter vault retrieval.** Instead of reading the whole `<language>-lessons.md`, extract only the 3–5 sections most relevant to `rough_goal`.

### Ecosystem upgrades

- **More language adapters** (`node-gates`, `go-gates`, `rust-gates`).
- **Gate type plugins** — third-party-contributable gate types without editing `measure_python.py`.

## How to pick up v0.4

After v0.3 has been used on at least one real project:
1. Read `~/.claude/skillgoid/metrics.jsonl` — which failure modes actually happened?
2. Read that project's `retrospective.md` and vault additions — which v0.4 items would have helped most?
3. Re-rank by observed ROI, not predicted ROI.
4. Spec the top 2–3 items using the same brainstorming → spec → plan → subagent-driven-development flow.
