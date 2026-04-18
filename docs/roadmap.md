# Skillgoid roadmap

## Shipped

### v0 (2026-04-17)
The concept: criteria-gated build loop + compounding per-language vault.
Spec: `docs/superpowers/specs/2026-04-17-skillgoid-design.md`
Plan: `docs/superpowers/plans/2026-04-17-skillgoid-v0.md`

## In flight

### v0.2 — Production Hardening Bundle
Three structural upgrades so the criteria-gated loop survives real multi-chunk projects:
1. Subagent-per-chunk isolation (bounds context, prevents cross-chunk interference)
2. Deterministic stall detection + git-per-iteration (safer loops, free rollback)
3. Integration gate after all chunks (catches green-gates-broken-product)

Spec: `docs/superpowers/specs/2026-04-17-skillgoid-v0.2-production-hardening.md`

## Deferred — v0.3 goals

Items explicitly pushed out of v0.2's YAGNI list and other ideas surfaced during brainstorming. Re-examine these after v0.2 ships and has been exercised on at least one real project.

### Adaptive / judgment upgrades

- **Plan refinement mid-build.** After chunk N passes, if its iterations surfaced evidence that downstream chunks are miscalibrated, let `build` re-invoke `plan` with the new evidence and update `chunks.yaml`. Current v0.2 surfaces to user instead. Unlocks handling projects where the right decomposition only becomes clear during implementation.

- **Pre-plan feasibility gate.** After `clarify` completes, a quick adversarial pass ("what's under-specified? what could break this?") before committing to the plan. Catches goals that look fine but are missing a key constraint.

- **Unstick skill.** Dedicated `/skillgoid:unstick` that takes a stalled chunk + one-sentence human hint and re-dispatches the chunk's subagent with the hint injected. Low-friction course-correction that preserves autonomy for everything else.

- **Rehearsal mode.** Before committing to `chunks.yaml`, cheaply simulate each chunk's first iteration (dry-run — no code written) to verify the chunks actually add up to the goal. Catches planning errors before burning iteration budget.

### Scale / throughput upgrades

- **Parallel chunks.** For chunks with no cross-dependency (already tracked via `depends_on`), dispatch their subagents concurrently. Combined with v0.2's integration gate this becomes safe — the gate catches interference at the end.

- **Polyglot / multi-language projects.** Per-chunk `language:` already exists in the schema. Needs: per-chunk adapter dispatch in `build`, vault retrieval across multiple `<language>-lessons.md` files, per-chunk fixture patterns.

- **Model tiering.** Haiku for gate measurement subagents (pure tool-use), Sonnet default for build subagents, Opus for `plan` / `clarify` / `retrospect` (judgment-heavy). Cuts cost on large projects.

### Observability upgrades

- **Telemetry / cross-project metrics.** Capture per-project stats: iterations-per-chunk, stall rate, gate-type failure distribution, vault-lesson hit rate. Emit to a user-global `~/.claude/skillgoid/metrics.jsonl`. Power a `/skillgoid:stats` command.

- **Dashboards.** Once metrics exist, a simple read-only report (markdown or plain HTML) showing trends across projects. Low priority — metrics data itself is the real value.

### Quality / safety upgrades

- **Coverage gate.** When `pytest` passes, also check test coverage hasn't regressed vs. previous iteration. Catches "tests pass because the feature doesn't exist yet" traps.

- **Diff-based reflection.** Iteration reflections capture not just "what failed" but "what changed between this iteration and the last." Makes stall analysis sharper and retrospectives more actionable.

- **Adapter timeouts.** Per-gate `timeout:` field. pytest or ruff can hang on a user's infinite-loop code; v0/v0.2 has no timeout. Default 300s.

- **Better `gate-guard` messaging.** Surface the failing-gate hints (not just IDs) in the block reason so the user immediately understands why Claude was asked to keep going.

- **Tighter vault retrieval.** Instead of reading the whole `<language>-lessons.md`, have `retrieve` extract only the 3–5 sections most relevant to the rough goal. Saves tokens on long-lived vaults.

### Ecosystem upgrades

- **More language adapters.** `node-gates`, `go-gates`, `rust-gates`. Community-writable via the template in `docs/custom-adapter-template.md`. Each ships as its own plugin or bundled.

- **Gate type plugins.** A gate-type registry so third-party adapters can contribute gate types (e.g., `type: playwright-smoke`) without modifying `measure_python.py`.

## How to pick up v0.3

After v0.2 has been used on at least one real project:
1. Read that project's `retrospective.md` and vault additions — which v0.3 items would have helped most?
2. Re-rank by observed ROI, not predicted ROI.
3. Spec the top 2–3 items using the same brainstorming → spec → plan → subagent-driven-development flow.
