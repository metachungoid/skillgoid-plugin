---
name: retrospect
description: Use after all chunks have passed their gates (or on explicit user request). Writes `.skillgoid/retrospective.md` summarizing the project, then curates notable iteration reflections into the user-global `~/.claude/skillgoid/vault/<language>-lessons.md`. Dedupes against existing entries and compresses older entries when the file exceeds 8K tokens.
---

# retrospect

## What this skill does

Two outputs:
1. **Project-local:** `.skillgoid/retrospective.md` — what worked, what didn't, what the final state is.
2. **User-global:** an *updated* `<language>-lessons.md` (and/or `meta-lessons.md`) in the vault, with this project's notable reflections integrated, deduped, and compressed if over the 8K-token threshold.

## Procedure

Step A — write the retrospective
1. Read all `.skillgoid/iterations/*.json` in order.
2. Read `.skillgoid/goal.md`, `.skillgoid/blueprint.md`, `.skillgoid/chunks.yaml`.
3. Write `.skillgoid/retrospective.md`:
   ```markdown
   # Retrospective — <goal title>

   ## Outcome
   <success | partial | abandoned>, final chunk state.

   ## What worked
   - ...

   ## What didn't
   - ...

   ## Surprises
   - <unexpected library behavior, wrong assumptions, design pivots>

   ## Stats
   - Chunks: N (M passed gates, K stalled)
   - Total iterations: T
   - Languages: <list>
   ```

Step B — curate the vault
4. Collect iteration records where `notable: true`. Extract the `reflection` text and surrounding context.
5. Determine target vault file(s): primary is `<language>-lessons.md`. If a reflection is language-neutral (e.g., about goal-clarification or gate-design), also/instead write it to `meta-lessons.md`.
6. Read the existing target file (if present).
7. **Integrate** the new notable reflections:
   - For each new reflection, look for related existing entries. If related, merge (prefer clearer language; keep the most recent specific example).
   - Add genuinely new lessons as new entries with a clear heading: `## <topic>`.
   - Drop or rewrite existing entries that the new project contradicts.
8. **Compress** if file > 8K tokens (approx 30KB):
   - Identify the least-recently-referenced entries (oldest `last_touched:` frontmatter or earliest section).
   - Summarize them into a trailing `## Distilled prior art` bullet list (one line per compressed entry).
   - Remove the full-length originals once summarized.
9. Write the updated file back.
10. Append a short log entry (optional): `~/.claude/skillgoid/vault/.log` records which projects contributed which lessons. Append-only, one line per contribution.

## File format for `<language>-lessons.md`

```markdown
# <language> lessons

<!-- curated by Skillgoid retrospect — edit with care -->

## <topic heading>

<the lesson, 1–4 paragraphs, concrete, with a specific example>

Last touched: YYYY-MM-DD by project "<slug>"

## <next topic>
...

## Distilled prior art

- <one-line summary of a compressed lesson>
- ...
```

## "Notable" rubric

A reflection is notable if it surfaces any of:
- A failure mode that took more than one attempt to diagnose.
- Unexpected behavior from a library, tool, or platform.
- A design decision that changed in response to new information.
- A gate that failed repeatedly for a non-obvious reason.

Routine green iterations are not notable. Do not promote them.

## Output

```
retrospect complete:
- retrospective.md written
- promoted N notable reflections to vault
- <language>-lessons.md updated (compression: <yes/no>)
```
