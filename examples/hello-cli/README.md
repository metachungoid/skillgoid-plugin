# Skillgoid end-to-end smoke test

To verify your install works:

```bash
mkdir -p /tmp/skillgoid-smoke && cd /tmp/skillgoid-smoke
cp <plugin-root>/examples/hello-cli/goal.md .
claude
```

Then in Claude Code:
```
/skillgoid:build "$(cat goal.md)"
```

You should see:
1. A clarifying Q&A pass.
2. Draft `goal.md` and `criteria.yaml` for your approval.
3. A `blueprint.md` and `chunks.yaml`.
4. One or more build iterations, each writing `.skillgoid/iterations/NNN.json`.
5. A `retrospective.md` when gates pass.
6. A new or updated `~/.claude/skillgoid/vault/python-lessons.md`.
7. A new line appended to `~/.claude/skillgoid/metrics.jsonl` summarizing the run (timestamp, slug, outcome, chunks, iterations, stalls, budget exhaustion, elapsed time).

If the `Stop` hook fires before completion with a message like "gates still failing", that's correct — it means the hook is wired up.
