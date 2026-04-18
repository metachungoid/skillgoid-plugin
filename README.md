# Skillgoid

**A Claude Code plugin that turns a rough project goal into a shipped codebase through a criteria-gated build loop with compounding cross-project memory.**

- **Define success** — measurable gates, not "I think it's done".
- **Build → measure → reflect** — loop until the gates pass.
- **Learn across projects** — a curated per-language lessons file grows smarter with every project.

## Install

```bash
claude plugin install <git-url-or-local-path>
```

Or for local development:
```bash
git clone https://github.com/metachungoid/skillgoid-plugin.git
cd skillgoid-plugin
claude plugin install .
```

## 60-second quickstart

1. Open a fresh, empty directory.
2. In Claude Code, run:
   ```
   /skillgoid:build "a Python CLI that syncs my Notion tasks to a local JSON file"
   ```
3. Answer a few clarifying questions when prompted.
4. Approve the draft `goal.md`, `criteria.yaml`, and `chunks.yaml`.
5. Skillgoid builds chunk-by-chunk, measuring gates each iteration. You watch (or step away). When the loop stalls or completes, you'll see a summary.
6. On success, a `retrospective.md` lands in `.skillgoid/` and notable lessons are curated into `~/.claude/skillgoid/vault/python-lessons.md`.

## What's new in v0.3

Six additive polish items, zero architectural change:

- **Adapter timeouts.** Every gate accepts an optional `timeout: <seconds>` (default 300). Runaway tests or hung CLIs fail fast with a clear hint.
- **Coverage gate.** New gate type `coverage` — honors `min_percent` and optional `compare_to_baseline` regression detection. Catches the "tests pass because the feature doesn't exist yet" trap.
- **Diff-based reflection.** Each iteration record now includes a `changes` field (files touched, net lines, summary) derived from the per-iteration git diff. Sharpens stall analysis and retrospect.
- **Better `gate-guard` messages.** When the Stop hook blocks mid-loop, it now surfaces the top-2 failing gate hints so you can decide whether to continue without reading iteration JSON.
- **Model tiering.** Optional `models:` block in `criteria.yaml` lets you override chunk/integration subagent models per-project (`haiku`/`sonnet`/`opus`).
- **Cross-project metrics scaffolding.** Retrospect now appends one JSON line per project to `~/.claude/skillgoid/metrics.jsonl`. Data accumulates locally; readers/dashboards come later.

All changes are fully backward-compatible with v0.2.

## What's new in v0.2

Three structural upgrades that make the build loop credible on real projects:

- **Subagent-per-chunk isolation.** Each chunk runs in a fresh subagent with a curated context slice — the main session stays small, cross-chunk interference goes away, and long projects no longer burn tokens on accumulated context.
- **Deterministic stall detection + git-per-iteration.** Stalls are now detected by hash comparison, not judgment. Every iteration produces a git commit (`skillgoid: iter N of chunk <id> …`) for free rollback targets. Opt out with `loop.skip_git: true` in `criteria.yaml`.
- **Integration gate.** Opt-in `integration_gates:` block in `criteria.yaml` runs after all per-chunk gates pass — catches "green gates, broken product" failures. Up to 2 auto-repair retries before surfacing.

All changes are backward-compatible. Existing v0 projects resume unchanged.

## Concepts

- **`.skillgoid/`** — project-local state: `goal.md`, `criteria.yaml`, `blueprint.md`, `chunks.yaml`, `iterations/NNN.json`, `retrospective.md`.
- **`~/.claude/skillgoid/vault/`** — user-global curated lessons: one `<language>-lessons.md` per language, plus optional `meta-lessons.md`.
- **Gates** — structured measurements (`pytest`, `ruff`, `mypy`, `import-clean`, `cli-command-runs`, `run-command`). Loop termination is defined in terms of these.
- **Acceptance scenarios** — free-form success stories. Inform test-writing but do not block the loop.
- **Hooks** — `SessionStart` injects resume context; `Stop` warns when you try to stop mid-loop with failing gates.

## Commands

- `/skillgoid:build "<goal>"` — start a new project.
- `/skillgoid:build resume` — continue the current project.
- `/skillgoid:build status` — print chunk + iteration summary.
- `/skillgoid:build retrospect-only` — finalize even if gates didn't all pass.
- `/skillgoid:clarify`, `/skillgoid:plan`, `/skillgoid:loop`, `/skillgoid:retrieve`, `/skillgoid:retrospect` — sub-skills, directly invokable.

## Custom language adapters

Skillgoid v0 ships with `python-gates`. See [docs/custom-adapter-template.md](docs/custom-adapter-template.md) to write your own for Node, Go, Rust, etc.

## Design

Full spec: [docs/superpowers/specs/2026-04-17-skillgoid-design.md](docs/superpowers/specs/2026-04-17-skillgoid-design.md).

## License

MIT.
