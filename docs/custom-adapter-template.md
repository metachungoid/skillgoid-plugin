# Writing a custom Skillgoid gate adapter

A gate adapter is a single skill that, invoked with a project path + criteria, runs gates and returns a structured JSON report.

## Contract

**Input** (from the `loop` skill):
- `project_path`
- `criteria_path` (or criteria subset)
- optional `gate_ids` filter

**Output:**
```json
{
  "passed": true,
  "results": [
    {"gate_id": "string", "passed": true, "stdout": "...", "stderr": "...", "hint": "..."}
  ]
}
```

## Minimal skill skeleton

Create `skills/<language>-gates/SKILL.md`:

````markdown
---
name: <language>-gates
description: Use to measure gates for <language> projects. Invoked by the `loop` skill when chunk language is `<language>`.
---

# <language>-gates

## Procedure

1. Read criteria from the specified path, filter by gate_ids if provided.
2. For each gate, invoke the right tool (test runner, linter, etc.) and capture stdout/stderr/exit code.
3. Assemble the JSON report.
4. Return the report verbatim.
````

## Tips

- Prefer a small companion script in `scripts/measure_<language>.py` (or similar) and have the skill shell out to it. Skills are prose; scripts are code.
- Always return valid JSON on stdout even on partial failure. Never crash the adapter.
- If a gate type isn't supported, emit a failed result with `hint: "unsupported gate type: X"` — don't invent behavior.
