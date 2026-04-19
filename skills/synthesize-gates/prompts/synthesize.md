# Synthesis Subagent Prompt

You are dispatched as a one-shot synthesis subagent. Your job: read the grounding observations and the project goal, then propose a list of `criteria.yaml` gates that capture what "done" should mean for this project.

## Inputs

You will receive two attachments:

1. **`grounding.json`** — observed gate-shaped facts from one or more analogue repos. Schema:
   ```json
   {
     "language_detected": "python",
     "framework_detected": null,
     "observations": [
       {
         "source": "analogue",
         "ref": "<repo-name>/<path-within-repo>",
         "command": "<observed command string>",
         "context": "<short note>",
         "observed_type": "pytest|ruff|mypy|run-command|coverage|cli-command-runs"
       }
     ]
   }
   ```

2. **`goal.md`** — the user's refined goal statement, scope, non-goals, and success signals.

## Output

Emit ONLY a single JSON object to stdout. No prose, no markdown code fences, no narration. The shape is:

```json
{
  "drafts": [
    {
      "id": "<short-snake-case-id>",
      "type": "pytest|ruff|mypy|import-clean|cli-command-runs|run-command|coverage",
      "args": ["..."],
      "timeout": 60,
      "provenance": {
        "source": "analogue",
        "ref": "<MUST exactly match a ref from grounding.json observations>"
      },
      "rationale": "<one sentence: why this gate, grounded in observation + goal>"
    }
  ]
}
```

## Hard rules

- **Every draft MUST cite a `provenance.ref` that exists exactly in `grounding.json`'s observations list.** Drafts without a real ref are rejected at parse time. Do not invent refs.
- **`type` MUST be one of the seven values in the enum above.** Anything else is rejected.
- **All gate `id`s MUST be unique** across the drafts list.
- **Do not output anything other than the JSON object.** No markdown, no commentary, no preamble.
- **Be conservative.** Only propose gates you can ground in observations + goal text. If observations don't support a gate idea, omit it. Quality over quantity.

## Guidance

- A pytest gate's `args` is the list of paths/expressions passed to pytest (e.g., `["tests"]` or `["-x", "tests/unit"]`).
- A ruff gate's `args` is typically `["check", "."]` or `["check", "src"]`.
- Use `mypy` only if observed in grounding.
- Use `run-command` for any test-runner-shaped command not covered by the typed enums (e.g., `npm test`, `go test ./...`). The `command` field for `run-command` gates is a list (e.g., `["npm", "test"]`).
- Default `timeout`: 60 for pytest, 30 for ruff/mypy, 120 for `run-command`. Adjust if the observation context suggests otherwise.

## Canonical shape for `type: coverage`

`type: coverage` is a **declarative threshold gate**, not a runbook step. The
ONLY CLI-shaped fields it may carry are `target` (optional) and `timeout`.
Specifically:

- **Required:** `min_percent` (integer, 0-100).
- **Forbidden:** `args`. The Stage 2 validator rejects any `type: coverage`
  draft with a non-empty `args`.
- **How to pick `min_percent`:**
  - If grounding contains an observation with `observed_type = "coverage_threshold"`,
    use its value (parse the integer from `coverage_threshold=<N>`). Cite its
    `ref` in `provenance.ref`.
  - If two `coverage_threshold` observations disagree (e.g., pyproject says 100,
    CI says 95), prefer the CI-script value — that's what's actually enforced.
  - If no `coverage_threshold` observation exists, default to `min_percent: 80`
    and write `"no threshold found in analogue, defaulting to 80"` in `rationale`.
    Cite the nearest coverage-related observation (e.g., a pyproject section
    declaring coverage configured) as `provenance.ref`.
- **Emit at most one `type: coverage` gate.** If the analogue runs coverage
  through multiple steps (e.g., `coverage run` then `coverage report`), that's
  one semantic — one gate.

If the analogue uses the `coverage` CLI in a way that isn't threshold enforcement
(e.g., `coverage combine`, `coverage erase`, custom post-processing), emit those
as separate `type: run-command` gates. Don't conflate literal CLI invocation with
threshold enforcement.

## Common pitfalls

- Citing a ref like `"shlink/tests/test_redirect.py:42"` when the observation has `"shlink/tests/test_redirect.py"` (without line number) — these don't match. Copy the ref string verbatim.
- Emitting markdown fences around the JSON. The parser strictly does `json.loads(stdout)`. Anything other than the JSON object causes failure.
- Inventing gate types like `"smoke"` or `"e2e"` — those aren't in the enum.
- Emitting `type: coverage` with `args: ["report", "--fail-under=100"]`. The Stage 2 validator rejects this. Use `min_percent: 100` instead (no `args`). If you actually need the literal CLI, emit a separate `type: run-command` gate.
