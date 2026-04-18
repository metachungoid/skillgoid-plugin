---
name: stats
description: Use when the user wants to see cross-project metrics — success rates, stalls, iterations per chunk, language distribution. Reads `~/.claude/skillgoid/metrics.jsonl` populated by `retrospect` and produces a markdown summary. Read-only; never modifies the metrics file. Invokable as `/skillgoid:stats` or `/skillgoid:stats <N>` for last-N projects.
---

# stats

## What this skill does

Reads the user-global metrics jsonl (populated one line per project by `retrospect` since v0.3) and produces a markdown summary of cross-project performance. Surfaces rollups + a recent-N table.

## When to use

- User asks "how's Skillgoid been performing lately?" / "what's my stall rate?" / "which languages have I built in?".
- After running several projects, to decide where to focus v0.X priorities based on observed failure modes.

## Inputs

- Optional `limit` — how many most-recent projects to show in the table. Default 20.
- Optional `metrics_file` path override — defaults to `~/.claude/skillgoid/metrics.jsonl`.

## Procedure

1. Invoke:
   ```bash
   python <plugin-root>/scripts/stats_reader.py [--limit <N>] [--metrics-file <path>]
   ```
2. The script emits a markdown report on stdout. Pass it through to the user unchanged.

## Output format

```markdown
# Skillgoid stats

**N projects tracked**

## Rollups
- Success rate: 80.0%
- Stall rate: 10.0%
- Budget-exhaustion rate: 5.0%
- Integration-retry rate: 20.0%
- Avg iterations per chunk: 1.50

## Languages
- python: 8
- node: 2

## Last N projects
| date | slug | lang | outcome | chunks | iters | stalls | retries | elapsed |
| 2026-04-17 | jyctl | python | success | 3 | 4 | 0 | 1 | 238s |
...
```

## What this skill does NOT do

- Write to or modify `metrics.jsonl`.
- Render HTML or graphs (that's v0.5+ dashboards work).
- Fetch remote metrics.
