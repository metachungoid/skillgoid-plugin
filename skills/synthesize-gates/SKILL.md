---
name: synthesize-gates
description: Use when the user wants to author `.skillgoid/criteria.yaml` from observation rather than from scratch. Given one or more analogue reference repos, the skill grounds observations, dispatches a synthesis subagent, validates the proposed gates against the criteria schema, runs oracle validation against the analogue and an empty scaffold, then writes `.skillgoid/criteria.yaml.proposed` with per-gate provenance + `validated: oracle | smoke-only | none` labels. v0.11: oracle validation is on by default; pass `--skip-validation` to bypass. Invokable as `/skillgoid:synthesize-gates <repo-url-or-path> [<repo2> ...]`.
---

# synthesize-gates

## What this skill does

Produces a draft `criteria.yaml` from observation of one or more analogue reference repositories. Each proposed gate carries a provenance comment so the user can trace it back to a real source. Output goes to `.skillgoid/criteria.yaml.proposed` — never overwrites existing `criteria.yaml`.

## When to use

- The user has a project goal in `.skillgoid/goal.md` and points to one or more reference repos as inspiration.
- The user explicitly invokes `/skillgoid:synthesize-gates <repo-url-or-path>`.
- After a `/skillgoid:clarify` run, when the user prefers synthesized gates over hand-authored.

**NOT** for:

- Projects with no analogue at all (Phase 1 requires at least one — Phase 2 will add context7 + curated templates as fallbacks).
- Modifying an existing committed `criteria.yaml` directly (always writes to `.proposed` for the user to merge).

## Inputs

- One or more analogue repo references, each either:
  - A git URL — `ground.py` shallow-clones it (depth=1) into `~/.cache/skillgoid/analogues/<slug>/`.
  - A local filesystem path — symlinked or referenced directly.
- `.skillgoid/goal.md` — must already exist (run `/skillgoid:clarify` first if absent).

If no analogues are provided as args, the skill interactively prompts for at least one. Phase 1 has no fallback to context7 / templates — at least one analogue is required.

**Flags:**

- `--skip-validation` — bypass oracle (Stage 3). Every gate lands `validated: none, warn: validation skipped by --skip-validation`.
- `--validate-only` — skip Stages 1, 2. Re-run Stage 3 + Stage 4 against the existing `drafts.json`. Use after installing analogue deps to refresh validation without re-synthesizing.

## Procedure

1. **Verify `.skillgoid/goal.md` exists.** If not, error: `"goal.md missing — run /skillgoid:clarify first."` Do not proceed.

2. **Collect analogue args.**
   - Accept each arg as-is. `ground.py` detects URLs (http/https/git@/ssh/git/file) vs local paths and shallow-clones URL analogues into the user-global cache dir (`~/.cache/skillgoid/analogues/<slug>/` on Linux; overridable via `$XDG_CACHE_HOME`).
   - If zero analogues given on CLI, prompt the user: `"No analogue repo provided. Please give a URL or local path to a reference project: "`. Read one line, treat as a single analogue.

3. **Run Stage 1 (grounding).** Shell out:
   ```bash
   python <plugin-root>/scripts/synthesize/ground.py \
     --skillgoid-dir .skillgoid \
     <analogue1-path> [<analogue2-path> ...]
   ```
   On non-zero exit, surface stderr to the user and stop.

4. **Verify grounding has at least one observation.** Read `.skillgoid/synthesis/grounding.json`. If `observations` is empty, error: `"No observations could be extracted from the analogue repo(s). Phase 1 requires at least one observable test or CI command."` Do not dispatch the subagent.

5. **Dispatch the synthesis subagent.** Use the Agent tool with:
   - `description`: `"Synthesize gates"`
   - `prompt`: contents of `skills/synthesize-gates/prompts/synthesize.md`, followed by two `<attachment>` blocks containing `grounding.json` and `goal.md` verbatim.
   - `subagent_type`: `"general-purpose"`
   - Model: default (sonnet).

   Capture the subagent's final text output as `subagent_stdout`.

6. **Run Stage 2 (parse + validate), with one auto-retry.**

   **Attempt 1.** Shell out:
   ```bash
   echo "$subagent_stdout" | python <plugin-root>/scripts/synthesize/synthesize.py \
     --skillgoid-dir .skillgoid
   ```
   On exit 0, proceed to step 7. On exit 1, capture the parser's stderr as `attempt1_stderr` and proceed to Attempt 2.

   **Attempt 2.** Re-dispatch the synthesis subagent with the **same** Agent-tool invocation as step 5, but append this block to the end of the `prompt` string (after the two `<attachment>` blocks):

   > Your previous output failed Stage 2 validation with:
   > ```
   > {attempt1_stderr}
   > ```
   > Re-emit the drafts JSON with this problem fixed. Do not include any prose — only valid JSON.

   Capture the retry's final text output as `retry_stdout`. Shell out:
   ```bash
   echo "$retry_stdout" | python <plugin-root>/scripts/synthesize/synthesize.py \
     --skillgoid-dir .skillgoid
   ```
   On exit 0, proceed to step 7 (the retry is the canonical drafts.json). On exit 1, capture stderr as `attempt2_stderr`, surface both messages to the user, and STOP:

   > Synthesis subagent failed Stage 2 validation twice. Re-run the skill or hand-author `.skillgoid/criteria.yaml`.
   >
   > Attempt 1 stderr:
   > {attempt1_stderr}
   >
   > Attempt 2 stderr:
   > {attempt2_stderr}

7. **Run Stage 3 (validate).** Shell out:
   ```bash
   python <plugin-root>/scripts/synthesize/validate.py \
     --skillgoid-dir .skillgoid
   ```
   Forward `--skip-validation` from the invocation if the user passed it. On non-zero exit, surface stderr and STOP. On zero exit, `.skillgoid/synthesis/validated.json` exists and labels each gate `oracle | smoke-only | none` with optional warn text.

   **For `--validate-only` invocations:** skip steps 3–6. Verify `.skillgoid/synthesis/grounding.json` and `.skillgoid/synthesis/drafts.json` both exist; if either is missing, error: `"--validate-only requires a prior full synthesis run. Re-run /skillgoid:synthesize-gates <analogues> first."` Then jump directly to this step, then step 8.

8. **Run Stage 4 (write).** Shell out:
   ```bash
   python <plugin-root>/scripts/synthesize/write_criteria.py \
     --skillgoid-dir .skillgoid
   ```

9. **Print the next-step summary** to the user:
   ```
   synthesize-gates: wrote .skillgoid/criteria.yaml.proposed

   Next:
     diff .skillgoid/criteria.yaml .skillgoid/criteria.yaml.proposed
     (or open .skillgoid/criteria.yaml.proposed in your editor)

   When you're happy with the gates, replace criteria.yaml with the .proposed
   version and run /skillgoid:build.
   ```

## Output

On success: `.skillgoid/criteria.yaml.proposed` is written. Existing `.skillgoid/criteria.yaml` is untouched. Per-stage artifacts are visible under `.skillgoid/synthesis/` (`grounding.json`, `drafts.json`). Analogue clones live under the user-global cache dir, not the project.

On failure: a single error line on stderr naming the failed stage. Partial artifacts under `.skillgoid/synthesis/` may remain — these are safe to inspect or delete.

## Phase 1 / 2 progress

- **v0.11 (current)**: Oracle validates analogue-cited gates. Every rendered gate carries a `validated: oracle | smoke-only | none` label derived from running the adapter against the analogue's cache-dir and an empty scaffold.
- **Remaining Phase 2 work (v0.13/v0.14)**: context7 grounding; curated template fallback for cold-start projects; oracle for context7/template-sourced gates.
- **v0.11.1**: one auto-retry on Stage 2 validation failure. If the subagent emits invalid drafts, the skill re-dispatches once with the rejection reason appended, then STOPs if the retry also fails.

## Risks

- Synthesis quality is bounded by the analogue quality. A poorly-tested analogue produces poorly-grounded gates.
- The `criteria.yaml.proposed` may include gate types the user's project doesn't need. The user is expected to delete unwanted gates during review.
- If two analogue repos use conflicting conventions (e.g., one uses pytest, the other uses unittest), the synthesis subagent picks one — the rationale field should explain why.
- `type: coverage` gates are now **declarative only**: `min_percent` required, `args` forbidden. Literal `coverage` CLI invocations must use `type: run-command`. Hand-authored criteria from pre-v0.10 that used the loose shape will fail schema validation at the build's feasibility stage — see the v0.10 release note for migration.
- `validated: oracle` means the gate *discriminated* the analogue from an empty scaffold. That's a strong signal but not a proof of correctness. Users reviewing the criteria should still sanity-check each gate against their project's actual expectations.
- Oracle runs the adapter in the user's current Python environment. If the analogue's test deps aren't importable, gates land `validated: none` with a warn line; install the analogue's deps (`pip install -e ~/.cache/skillgoid/analogues/<slug>[dev]`) and re-run with `--validate-only`.
