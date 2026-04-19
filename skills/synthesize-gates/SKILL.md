---
name: synthesize-gates
description: Use when the user wants to author `.skillgoid/criteria.yaml` from observation rather than from scratch. Given one or more analogue reference repos, the skill grounds observations, dispatches a synthesis subagent, validates the proposed gates against the criteria schema, and writes `.skillgoid/criteria.yaml.proposed` with per-gate provenance comments. Phase 1: user-pointed analogues only, no oracle validation, all gates labeled `validated: none`. Invokable as `/skillgoid:synthesize-gates <repo-url-or-path> [<repo2> ...]`.
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
- Validation of the gates' actual behavior (Phase 1 emits `validated: none`; Phase 2 adds oracle validation).

## Inputs

- One or more analogue repo references, each either:
  - A git URL — the skill clones it (shallow, depth=1) into `.skillgoid/synthesis/analogues/<slug>/`.
  - A local filesystem path — symlinked or referenced directly.
- `.skillgoid/goal.md` — must already exist (run `/skillgoid:clarify` first if absent).

If no analogues are provided as args, the skill interactively prompts for at least one. Phase 1 has no fallback to context7 / templates — at least one analogue is required.

## Procedure

1. **Verify `.skillgoid/goal.md` exists.** If not, error: `"goal.md missing — run /skillgoid:clarify first."` Do not proceed.

2. **Resolve analogue paths.**
   - For each git URL arg: shallow-clone into `.skillgoid/synthesis/analogues/<slug>/` where `<slug>` is the URL's owner+repo (e.g., `pallets-flask` for `github.com/pallets/flask`). Skip clone if directory already exists.
   - For each local path arg: verify the directory exists. Use the path as-is.
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

6. **Run Stage 2 (parse + validate).** Shell out:
   ```bash
   echo "$subagent_stdout" | python <plugin-root>/scripts/synthesize/synthesize.py \
     --skillgoid-dir .skillgoid
   ```
   If the parser exits non-zero, surface its stderr (which names the violated rule) and STOP. Do not retry the subagent in Phase 1 — surface the failure so the user can re-run or hand-author. Phase 2 will add a single auto-retry.

7. **Run Stage 4 (write).** Shell out:
   ```bash
   python <plugin-root>/scripts/synthesize/write_criteria.py \
     --skillgoid-dir .skillgoid
   ```

8. **Print the next-step summary** to the user:
   ```
   synthesize-gates: wrote .skillgoid/criteria.yaml.proposed

   Next:
     diff .skillgoid/criteria.yaml .skillgoid/criteria.yaml.proposed
     (or open .skillgoid/criteria.yaml.proposed in your editor)

   When you're happy with the gates, replace criteria.yaml with the .proposed
   version and run /skillgoid:build.
   ```

## Output

On success: `.skillgoid/criteria.yaml.proposed` is written. Existing `.skillgoid/criteria.yaml` is untouched. Per-stage artifacts are visible under `.skillgoid/synthesis/` (`grounding.json`, `drafts.json`) for debugging.

On failure: a single error line on stderr naming the failed stage. Partial artifacts under `.skillgoid/synthesis/` may remain — these are safe to inspect or delete.

## Phase 1 limitations (called out for users)

- All gates are labeled `validated: none (Phase 1: oracle validation deferred)`. The user is the only validator.
- No context7 grounding — only user-pointed analogues.
- No curated template fallback for cold-start projects.
- No retry on subagent output validation failure — re-run the skill if needed.

Phase 2 (planned) addresses all four.

## Risks

- Synthesis quality is bounded by the analogue quality. A poorly-tested analogue produces poorly-grounded gates.
- The `criteria.yaml.proposed` may include gate types the user's project doesn't need. The user is expected to delete unwanted gates during review.
- If two analogue repos use conflicting conventions (e.g., one uses pytest, the other uses unittest), the synthesis subagent picks one — the rationale field should explain why.
