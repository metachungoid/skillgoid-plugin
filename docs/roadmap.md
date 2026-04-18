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

## Deferred — v0.5 goals

Items pushed out of v0.4 for lack of real-world evidence. Re-rank after more runs populate `~/.claude/skillgoid/metrics.jsonl`.

### Adaptive / judgment (still highest predicted value)

- **Plan refinement mid-build.** The single biggest predicted complexity-ceiling lever, but zero real-run evidence yet. Architecturally risky (mutable plan during execution). Revisit after a real project hits a mid-flight replan need.

### Scale / throughput

- **Parallel chunks.** Now safer with v0.2's integration gate. Wall-clock wins on multi-chunk independent work.
- **Polyglot / multi-language projects.** Per-chunk adapter + vault across languages. Unlocks full-stack projects.

### Observability extensions

- **Rehearsal mode** — dry-run each chunk's first iteration before committing chunks.yaml. May overlap with v0.4's feasibility — revisit only if feasibility proves insufficient.
- **Dashboards / HTML rendering.** `/skillgoid:stats` markdown is enough until metrics.jsonl has 20+ entries.

### Quality / safety

- **Tighter vault retrieval.** Extract the 3–5 most relevant vault sections per goal instead of reading whole files. Only matters at vault scale (50+ projects).

### Ecosystem

- **More language adapters** (`node-gates`, `go-gates`, `rust-gates`).
- **Gate type plugins** — third-party-contributable gate types without editing `measure_python.py`.

## How to pick up v0.5

After v0.4 has landed and run on a few real projects:
1. Run `/skillgoid:stats` on accumulated metrics.
2. Look for the most common failure modes in the table.
3. Re-rank v0.5 items by what actually broke.
4. Spec the top 2–3 by observed ROI.
