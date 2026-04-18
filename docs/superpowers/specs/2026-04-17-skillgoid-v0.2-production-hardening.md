# Skillgoid v0.2 — Production Hardening Bundle

- **Date:** 2026-04-17
- **Status:** Draft, pre-implementation
- **Supersedes:** nothing — extends v0 (`2026-04-17-skillgoid-design.md`)
- **Scope:** three architectural upgrades that together make the criteria-gated loop credible on real multi-chunk projects

---

## 1. Goal & non-goals

### Goal

Take Skillgoid from "concept ships" to "architecturally credible at real project scale." Three weakness axes are addressed simultaneously:

1. **Complexity ceiling** — context bloat limits how many chunks a single project can run through before Claude's context window becomes the bottleneck.
2. **Output quality** — green per-chunk gates don't prove the system works end-to-end.
3. **Loop-exit reliability** — current stall detection is Claude-judged rather than deterministic.

### Non-goals (v0.2)

- **Parallel chunks.** Independent chunks still run sequentially. Parallelism creates integration stress and merge-reconciliation work not worth the cost until subagent isolation is proven.
- **Adaptive plan refinement mid-build.** The plan remains one-shot. If a chunk surfaces evidence that downstream chunks are wrong, v0.2 still surfaces to the user — no auto-replan.
- **Polyglot / multi-language projects.** One language per chunk continues; one adapter per language continues.
- **Model tiering.** Not wired up in v0.2 — isolating the subagent-dispatch change keeps the blast radius small.
- **Unstick skill / mid-loop human hinting.** v0.3 material.
- **Telemetry / cross-project metrics / dashboards.** v0.3+.

---

## 2. Why this exists

v0 was intentionally minimal — it ships the *concept* of a criteria-gated loop with compounding memory. The final code review of v0 flagged three latent weaknesses that don't matter on a 2-chunk hello-cli smoke test but will dominate a 5–10 chunk real project:

| Weakness | How it manifests | v0.2 remedy |
|---|---|---|
| Loop runs in main session → context bloat | By chunk 5 iteration 3, the session's context contains all prior chunk iterations + all gate reports. Token cost climbs, quality drops, stalls go unnoticed. | **Subagent-per-chunk isolation** — each chunk gets a fresh subagent with a curated context slice. |
| Stall detection is Claude-judged | Minor variance (timestamps, file paths in stderr) hides identical failures. Loop burns its whole budget on the same root cause. | **Deterministic stall signature** — sha256 hash of sorted failing gate IDs + stderr prefix. |
| No end-to-end verification | Per-chunk gates can all pass while the system as a whole fails to run. "Green gates, broken product." | **Integration gate** — new optional criteria section that runs *after* all chunk gates pass. |

A fourth, smaller addition — **git-per-iteration** — rides along with the stall work because it materially improves debuggability and rollback at trivial cost.

---

## 3. Architecture

### 3.1 Subagent-per-chunk isolation

The `build` orchestrator gains the role of **dispatcher**. Its new control flow:

```
build
├── retrieve (once, main session)   — compute vault summary for the rough goal
├── clarify (once, main session)    — write goal.md + criteria.yaml
├── plan    (once, main session)    — write blueprint.md + chunks.yaml
├── for each chunk in order:
│     └── Agent(subagent) — dispatched with a curated prompt:
│           • chunk entry (id, description, gate_ids, language)
│           • retrieve summary (verbatim)
│           • blueprint slice relevant to this chunk (headings/sections whose
│             titles match chunk id or description keywords — heuristic in plan skill)
│           • last 1–2 iterations/*.json for this chunk (if resuming)
│           → instructs subagent to invoke `skillgoid:loop` for this chunk
│           → subagent returns: {exit_reason, iterations_used, final_gate_report}
├── if any chunk exits stalled/budget_exhausted → stop, surface to user
├── integration gates (see §3.3)
└── retrospect (once, main session)
```

**Why a subagent, not just a sub-skill invocation:**
- The main session never holds the per-chunk working context. A 10-iteration chunk that burned 40K tokens disappears when the subagent returns; only the summary remains.
- Each chunk starts from the same baseline context envelope. Chunk 7 is not "chunk 1's context plus chunks 2–6's context plus chunk 7's work." It's just "chunk 7's work."
- Subagents can be killed/retried without corrupting the orchestrator's state.

**Subagent prompt template** (pseudo-yaml, lives in the `build` skill):

```
subagent_type: general-purpose
model: sonnet  (rationale: chunk work needs judgment + tool use; cheaper than opus)
description: "Execute Skillgoid chunk <chunk_id>"
prompt: |
  You are executing one chunk of a Skillgoid build loop.

  ## Chunk spec
  {chunk_yaml_entry}

  ## Relevant past lessons
  {retrieve_summary}

  ## Relevant blueprint sections
  {blueprint_slice}

  ## Prior iterations for this chunk (if any)
  {last_two_iterations}

  ## Your job
  Invoke `skillgoid:loop` with chunk_id="{chunk_id}". When it returns,
  summarize: exit_reason, iterations_used, final gate_report, and any
  notable observations. Do not invoke retrospect — the orchestrator will.

  Return a JSON object: {"exit_reason": ..., "iterations_used": ...,
  "final_gate_report": ..., "notes": "<1-3 sentences>"}
```

**What the main session remembers** across chunks: only the per-chunk return summaries (~200–500 tokens each). A 10-chunk project's orchestrator context stays well under any practical limit.

### 3.2 Deterministic stall detection + git-per-iteration

#### Stall signature

New helper: `scripts/stall_check.py`.

```python
import hashlib, json, sys
from pathlib import Path

def signature(record: dict) -> str:
    report = record.get("gate_report") or {}
    failing = sorted(
        r.get("gate_id", "") for r in report.get("results", []) if not r.get("passed")
    )
    stderr_blob = "".join(
        (r.get("stderr") or "")[:200]
        for r in report.get("results", [])
        if not r.get("passed")
    )
    payload = f"{failing}::{stderr_blob}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def main():
    path = Path(sys.argv[1])
    rec = json.loads(path.read_text())
    print(signature(rec))


if __name__ == "__main__":
    main()
```

Contract:
- CLI: `python scripts/stall_check.py <iterations/NNN.json>` prints a 16-char hex signature.
- Library: importable as `from scripts.stall_check import signature`.
- Identical failure payloads → identical signature. Minor noise (timestamps, absolute paths in stdout, wall-clock variance) is excluded because it's not part of stderr prefix + failing gate IDs.

`loop` skill writes this as `failure_signature` inside every `iterations/NNN.json`. Stall = current iteration's signature equals previous iteration's signature.

#### Git-per-iteration

`loop` skill, at the end of each iteration:

1. Check: `git rev-parse --is-inside-work-tree` — if false, skip all git steps (noop).
2. `git add -A`
3. `git commit -m "skillgoid: iter N of chunk <id> (<exit|in_progress>)\n\nGates: pytest (fail), ruff (pass)\nSignature: <16-char>"` with `--allow-empty` so zero-diff iterations still commit.
4. On failure of the `git` command itself (user mid-rebase, hooks failing, detached head, etc.), log the failure to stderr and continue — never block the loop on git.

Rollback shape for users:
- Every failed iteration is a commit with a parseable message.
- `git log --grep='^skillgoid:'` surfaces just the loop commits.
- `git reset --hard HEAD~1` undoes the last failing iteration's code changes; `git reset --hard <sha>` jumps to any specific prior attempt.
- The iteration JSON itself is committed alongside the code, so rollback restores matching state.

#### Opt-out

Projects that don't want Skillgoid commits in their history can set `loop.skip_git: true` in `criteria.yaml`. Schema extension.

### 3.3 Integration gate after all chunks

Adds a new optional top-level field to `criteria.yaml`:

```yaml
integration_gates:
  - id: cli_smoke
    type: cli-command-runs
    command: ["myapp", "greet", "--name", "World"]
    expect_stdout_match: "hello, World!"
  - id: e2e_tests
    type: pytest
    args: ["tests/integration", "-v"]
integration_retries: 2   # optional, default 2
```

Gate item shape is **identical** to per-chunk gates. The only semantic difference is *when* they run: after all chunk subagents succeed.

#### Flow

```
build
 … all chunks pass …
 ├── dispatch integration subagent (fresh context):
 │     ├── invoke skillgoid:python-gates with integration_gates
 │     └── return gate_report
 │
 ├── if passed → retrospect
 ├── if failed:
 │     ├── surface failure to user (list failing gates + stderr)
 │     ├── attempt auto-repair:
 │     │     ├── identify suspect chunk(s): pick chunks whose files
 │     │     │    appear in stderr paths (simple grep-based heuristic);
 │     │     │    if none, ask user which chunk to retry
 │     │     ├── re-dispatch that chunk's loop subagent with
 │     │     │    integration-failure context added ("when full system
 │     │     │    runs, X happens. Your chunk's tests pass. Something
 │     │     │    about <suspect file> is still wrong.")
 │     │     └── re-run integration subagent
 │     ├── allow up to integration_retries (default 2) full rounds
 │     └── on exhaustion → surface to user, do not retrospect automatically
```

#### Why a subagent for integration

Same reasons as per-chunk. The integration check is its own piece of work with its own context; running it in the main session leaks whatever state happened to be there. Fresh subagent = clean baseline.

#### Default from `clarify`

The `clarify` skill, when drafting `criteria.yaml`, adds a suggested integration gate by default for:

- **CLI projects**: `cli-command-runs` against the CLI's main help flag or a minimal command (e.g., `greet --name World`).
- **Libraries**: `import-clean` of the top-level package followed by a trivial programmatic call.
- **Services**: a run-command starting the service, hitting a health endpoint, and shutting it down (if the user can describe the commands).
- **Unknown/ambiguous**: omit — leave `integration_gates` empty; user can add later.

Users can always strip or rewrite the suggested gate before approving `criteria.yaml`.

---

## 4. Data layout changes

### 4.1 `.skillgoid/iterations/NNN.json` — field addition

Existing fields preserved. New field:

```json
{
  "iteration": 3,
  "chunk_id": "core-api",
  "started_at": "...",
  "ended_at": "...",
  "gates_run": ["pytest", "ruff"],
  "gate_report": { ... },
  "reflection": "...",
  "notable": true,
  "failure_signature": "a3f2b8c1d4e5f601",   // NEW — always present
  "exit_reason": "in_progress" | "success" | "budget_exhausted" | "stalled"
}
```

v0 records without `failure_signature` still parse; readers treat missing signature as "unknown, cannot stall-check."

### 4.2 `criteria.yaml` — field additions

Existing fields preserved. New optional fields:

```yaml
integration_gates:          # optional; array of gate items (same shape as gates[])
  - ...
integration_retries: 2      # optional; default 2; integer ≥ 0

loop:
  max_attempts: 5
  skip_git: false           # NEW optional; default false (git-per-iteration on)
```

Schema update in `schemas/criteria.schema.json`.

### 4.3 `.skillgoid/integration/` — new optional subdir

If integration runs, `build` writes the integration attempt records here:

```
.skillgoid/integration/
  ├── 001.json     — first attempt
  ├── 002.json     — first auto-repair retry
  └── 003.json     — second auto-repair retry
```

Same shape as `iterations/NNN.json` but without `chunk_id` (or `chunk_id: "__integration__"` sentinel).

### 4.4 No vault changes

`~/.claude/skillgoid/vault/` is untouched. Retrospect still curates there.

---

## 5. Skill-level changes

### `skills/build/SKILL.md`

Rewritten. New responsibilities:

- Dispatcher — dispatches one Agent subagent per chunk and one for integration.
- State reducer — reads per-chunk subagent returns, updates orchestration summary, decides whether to proceed.
- Integration orchestrator — runs the integration subagent, handles retries and auto-repair re-dispatches.

Does NOT do per-iteration work itself.

### `skills/loop/SKILL.md`

Small updates:

- Procedure step 8 (reflect) — after writing `iterations/NNN.json`, run `scripts/stall_check.py` and store the signature back into the same file.
- Procedure step 8.1 (new) — git commit the iteration (guarded on git-repo + `loop.skip_git != true`).
- Exit-condition evaluation order unchanged, but stall check is now: `current.failure_signature == previous.failure_signature`.

Loop still runs inside a chunk subagent. The skill doesn't know or care whether its caller is the main session or a subagent — it behaves the same either way.

### `skills/clarify/SKILL.md`

Small addition:
- When drafting `criteria.yaml`, propose one sensible default `integration_gates` entry per §3.3.

### `skills/plan/SKILL.md`

Small addition:
- Blueprint sections should have clear headings per module/chunk so the `build` dispatcher can slice them reliably.

### `skills/retrieve/SKILL.md`, `skills/retrospect/SKILL.md`, `skills/python-gates/SKILL.md`

No changes required.

---

## 6. Hooks

No changes to `detect-resume.sh`. 

`gate-guard.sh`: consider (low priority) also checking `integration/` records in addition to `iterations/` so it can block Stop when integration is mid-failure. Deferred — `iterations/` coverage alone catches the common case.

---

## 7. Testing strategy

- **Unit test** `stall_check.py` — same failing-gate IDs + same stderr prefix → same signature; differ in either → different signature. ~5 assertions.
- **Unit test** integration gate runs via `measure_python.py` — add one to `tests/test_measure_python.py` exercising a fixture project against an "integration" gate set (just another gate set, same adapter).
- **Schema test** — valid `integration_gates` array passes; malformed entries fail; `skip_git` accepts boolean; `integration_retries` accepts ≥0.
- **Git-per-iteration test** — in `tests/test_git_commits.py`, use `tmp_path` as a git repo, simulate an iteration JSON, invoke the git-commit helper (factored out of the loop skill's prose into a small helper script or bash function), assert a commit landed with the expected message shape.
- **Integration test** (end-to-end) — extend `tests/test_integration.py`. A 2-chunk fixture where chunk-level gates pass but an integration gate fails → verify `build`'s auto-repair path is taken (this test probably asserts against an `integration/*.json` file being written, not against a live Claude session).
- **No test** for the subagent dispatch mechanics themselves — that requires a real Claude Code session. Relies on Claude Code's Agent-tool guarantees.

Expected total test count after v0.2: ~35 (currently 28 + ~7 new).

---

## 8. Backward compatibility

- v0 `criteria.yaml` loads cleanly; `integration_gates` absent → `build` simply skips that step.
- v0 `iterations/*.json` loads cleanly; missing `failure_signature` → stall check treats as "unknown, can't stall."
- v0 `.skillgoid/` layouts work unchanged.
- Projects not in git: no commits made, nothing breaks.
- Users who dislike Skillgoid's commit messages: set `loop.skip_git: true`.

No migration needed. v0 projects resumed under v0.2 Just Work.

---

## 9. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Subagent dispatch from a skill doesn't work as expected in the current Claude Code version | Low (Agent tool is first-class) | Smoke-test the dispatch in Task 1 or 2 of the plan against a trivial chunk before building out more. Document fallback: if dispatch misbehaves, `build` falls back to invoking `skillgoid:loop` inline (v0 behavior). |
| Blueprint "slice" heuristic (match chunk id/keywords to headings) is too coarse or too narrow | Medium | Default to passing the whole `blueprint.md` in early versions; tighten only if context bloat is observed. |
| Git-per-iteration commits pollute the user's git history | Medium | Opt-out via `loop.skip_git: true`. Commit messages are parseable (`skillgoid:` prefix) so they can be filtered/squashed. |
| Integration auto-repair picks the wrong chunk and makes things worse | Medium | Hard cap at `integration_retries` (default 2). If auto-repair exhausts, surface failure details and stop — never silently loop forever. Never destructively rewrite prior chunks' gates. |
| False-positive stall when natural noise varies stderr | Low | Signature excludes timestamps and only uses first 200 chars of stderr. If a real project hits natural variance, user can increase `max_attempts` to absorb it. |
| Subagent model choice (`sonnet`) wrong for a given chunk | Low | Hardcoded in v0.2. Model tiering per chunk is v0.3. |

---

## 10. Open questions for the planning pass

1. **Blueprint slicing heuristic** — do we actually implement keyword-matching, or punt and pass whole `blueprint.md` in v0.2? I'd lean punt; tighten in v0.3 if needed.
2. **Integration auto-repair suspect detection** — purely heuristic (grep filenames from stderr against chunks) or delegate to a tiny LLM judgment step? Simplest: start heuristic, fall back to "ask user" if no files match.
3. **Iteration JSON schema** — should we ship a JSON Schema for it in `schemas/iterations.schema.json` now to lock in the shape, or keep it implicit? Probably add — helps v0.3 evolution.
4. **Integration gate subagent model** — same Sonnet default as chunk subagents, or Haiku (it's just running gates and reporting)? Probably Haiku — pure measurement, no judgment.
5. **Retry back-off** — should auto-repair retries have any delay between them, or fire immediately? Immediate is fine for v0.2.

---

## 11. Skill-level invocation diagram (v0.2)

```
user → /skillgoid:build "<goal>"
         │
         ▼
   main session
     │
     ├── skillgoid:retrieve (in-session)
     ├── skillgoid:clarify  (in-session)
     ├── skillgoid:plan     (in-session)
     │
     │   For each chunk in chunks.yaml:
     ├── Agent(subagent, sonnet, "execute chunk X") ┐
     │                                              │
     │                                              ▼
     │                                        subagent session
     │                                          │
     │                                          └── skillgoid:loop
     │                                                ├── build step
     │                                                ├── skillgoid:python-gates
     │                                                ├── stall_check.py
     │                                                ├── git commit
     │                                                └── (loop until exit)
     │                                          returns summary
     │   ◄──────────────────────────────────────────────┘
     │
     ├── (after all chunks pass)
     ├── Agent(subagent, haiku, "run integration gates") ┐
     │                                                   │
     │                                                   ▼
     │                                             subagent session
     │                                               └── skillgoid:python-gates (integration_gates)
     │                                             returns report
     │   ◄───────────────────────────────────────────────┘
     │
     ├── (if integration fails: identify suspect chunk,
     │    re-dispatch chunk subagent, re-run integration,
     │    up to integration_retries)
     │
     └── skillgoid:retrospect (in-session)
```

---

## 12. Complexity budget

Estimated plan size: ~12 tasks across 3 bundles.

- Stall + git bundle: ~3 tasks (stall_check.py + tests, loop skill update, git-commit helper + tests)
- Integration gate bundle: ~4 tasks (schema update + tests, clarify update, build update for integration orchestration, integration test)
- Subagent dispatch bundle: ~4 tasks (build skill rewrite, loop/plan small updates, dispatch smoke test, end-to-end integration test)
- Docs + CI bundle: ~1 task (README section for v0.2 features + CHANGELOG)

No new skills (all changes are to existing skills and schemas + one new helper script).

---

## 13. What "done" looks like

v0.2 ships when:

- All v0 tests still pass.
- New tests pass (~7 new, ~35 total).
- A real end-to-end smoke test on `examples/hello-cli` exercises the subagent-per-chunk path (manually — no automated end-to-end against a live Claude session).
- The README's quickstart still accurately reflects user experience (no new user-visible commands, just better behavior behind the scenes).
- CHANGELOG notes the three upgrades + backward-compat guarantees.
