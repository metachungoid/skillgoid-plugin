# Skillgoid v0.8 — Correctness + Subagent Discipline Bundle

**Status:** spec
**Date:** 2026-04-18
**Predecessor:** v0.7 Correctness Bundle (commits `5c966f3` + `40a4b7b`, tag `v0.7.0`)
**Evidence source:** minischeme stress run (2026-04-18). Findings: `~/Development/skillgoid-test/v0.8-findings.md`. Retrospective: `~/Development/skillgoid-test/minischeme/.skillgoid/retrospective.md`. Metrics: `~/.claude/skillgoid/metrics.jsonl` (slug `minischeme-stress`).

## Context

The minischeme stress test (18-chunk Lisp interpreter, 6 concurrent subagents in the headline wave) confirmed v0.7's correctness fixes at 3× the scale they were validated at in unit tests. But it also surfaced 7 new findings that the machinery didn't catch. All 7 are real — observed in a live run, not speculated. Deferring any of them would be deferring against evidence.

Seven findings group naturally into five items:

- **F5 + F9:** iteration JSON schema drift silently accepted. One subagent wrote `status`/`gates` instead of `exit_reason`/`gate_report`; another wrote `iteration: "001"` (string) instead of `1`. No validation step in the loop or commit helper caught either. Commit message read `"(in-progress)"` for a passing 17/17-tests chunk because `_build_message` couldn't find `gate_report.passed`. Downstream readers that iterate `gate_report.results[]` will KeyError on one of these records.
- **F8:** same-file concurrent modification commits code under the wrong chunk's message. `tail-calls` and `error-handling` both modified `evaluator.py` in wave 6; the flock serialized their commits, but the one-committed-first absorbed the other's changes. `git log --grep="tail-calls"` points to a commit that lacks the trampoline code. Per-chunk history becomes intent-inconsistent.
- **F3 + F12:** every parallel-wave subagent independently narrowed `pytest_chunk` args (F3) and `lint` args (F12) from the project-wide default to their own files, to insulate against sibling-in-flight issues. Reinventing the same defensive pattern each time.
- **F7:** blueprint slicing has been deferred since v0.2 ("passes whole file"). Minischeme produced the first concrete evidence that the prose-blueprint-passed-verbatim pattern causes ahead-of-scope work — Wave 4 (evaluator-core) wrote ALL of Wave 5's (special-forms) code. Wave 5's subagent found the work already done.
- **F6:** prose blueprints can't enforce type-identity contracts. `parser.py` subagent invented its own `_NilType` singleton despite `values.py` also defining one. Two distinct objects with identical names. Evaluator-core had to manually bridge them — a cognitive load that scales poorly.

This spec ships fixes for all five items. Zero items deferred.

## Goals

1. Add machinery-level enforcement of invariants the loop/commit pipeline currently trusts prose instructions to maintain.
2. Kill cross-chunk test/lint interference as a structural problem, not a defensive-pattern obligation.
3. Enable per-chunk context isolation (blueprint slicing) so subagents stop doing adjacent chunks' work.
4. Establish a blueprint convention that cross-chunk type contracts can actually live in.
5. Preserve full backward compatibility: every existing v0.7 project continues to work without modification.

## Non-goals

- Polyglot language support (requires 2-3 organic polyglot runs; v0.8 isn't that).
- Replacing prose blueprints with structured formats (too big; slicing is enough).
- `node-gates` or any other language adapter.
- Plan refinement mid-build. Zero evidence across 8 real runs. Formally close the question for v0.8: add a one-line note to the roadmap removing it from the deferred-with-speculation list entirely.
- Rehearsal mode, dashboards, broader retrieve/retrospect rewrites.
- The `F10` out-of-pipeline commit (tail-calls fixing a test in special-forms). Real but requires more evidence about how cross-chunk fixups should be handled; defer.
- The `F11` accidental double-commit (builtins-arith). Symptom of subagent discipline; the schema-validation work (F5/F9) should incidentally address it by making iteration-json-absent a loud error. If F11 recurs post-v0.8, revisit.

## Design

### Item 1 — Schema validation before commit (F5 + F9)

#### 1.1 New helper: `scripts/validate_iteration.py`

Tiny helper. Public surface:

```python
def validate_iteration(record: dict, schema_path: Path | None = None) -> list[str]:
    """Return list of validation errors (empty list = valid).
    schema_path defaults to schemas/iterations.schema.json next to the helper."""
```

CLI:

```
python scripts/validate_iteration.py <iteration-json-path>
```

Exit 0 if valid, exit 2 if invalid (error messages to stderr). Used both as a preflight tool and internally by `git_iter_commit.py`.

#### 1.2 `scripts/git_iter_commit.py` changes

After the existing `json.loads(iteration_path.read_text())` but BEFORE acquiring the flock:

```python
from scripts.validate_iteration import validate_iteration
errors = validate_iteration(record)
if errors:
    sys.stderr.write(
        f"git_iter_commit: iteration at {iteration_path} failed schema validation:\n"
    )
    for err in errors:
        sys.stderr.write(f"  - {err}\n")
    return 2
```

Failing iteration records are refused with clear error pointing at the bad fields. Commit does NOT happen. Caller sees exit 2.

#### 1.3 Rationale for strict-fail vs. warn

The error-handling subagent's bad record in the minischeme run produced a commit message reading `"(in-progress)"` for a passing chunk. That's the worst outcome: silently wrong. A loud failure forces the subagent to notice and correct its output.

#### 1.4 Tests

In `tests/test_validate_iteration.py`:

- Valid v0.7 record: no errors.
- Missing `gate_report`: error mentions `gate_report`.
- `iteration: "001"` (string instead of int): error mentions type mismatch.
- Unknown fields (additionalProperties is true in schema): no error (explicitly confirm back-compat with subagents that add non-standard keys).

In `tests/test_git_iter_commit.py` (extend):

- `test_invalid_iteration_hard_fails`: malformed JSON → main returns 2, stderr mentions validation.
- `test_valid_iteration_passes_through`: unchanged v0.7 commit path still works.

### Item 2 — Path-overlap auto-serialization (F8)

#### 2.1 `scripts/chunk_topo.py` changes

`plan_waves(chunks: list[dict]) -> list[list[str]]` gains a post-pass: after computing topological waves, scan each wave for chunks with overlapping `paths:`. Any wave containing overlap is split into consecutive sub-waves, each sub-wave containing non-overlapping chunks (alphabetical order by `chunk_id` for determinism).

Overlap definition: two chunks overlap if any entry in chunk A's `paths:` list matches any entry in chunk B's (exact-string match for v0.8; glob-aware matching deferred to v0.9 if evidence demands).

Example:
- Wave 6 input: `[builtins-arith, builtins-io, builtins-list, builtins-string, error-handling, tail-calls]`
- `error-handling` and `tail-calls` both have `paths: [src/minischeme/evaluator.py, ...]`
- Post-pass output: wave 6 becomes TWO waves:
  - Wave 6a: `[builtins-arith, builtins-io, builtins-list, builtins-string, error-handling]`
  - Wave 6b: `[tail-calls]` (alphabetically later, so serialized after error-handling)

#### 2.2 `skills/plan/SKILL.md` updates

New bullet under `## Principles`:

> - **Watch for same-file chunks in the same wave.** Two chunks that modify overlapping paths cannot safely commit in parallel (one's changes get committed under the other's chunk message). `chunk_topo` now auto-serializes these, but a clean blueprint avoids the overlap in the first place — either by splitting the work into disjoint files, or by making one chunk explicitly `depends_on` the other.

Add informational output to `chunk_topo.py` CLI: when a wave gets split, print a one-line note to stderr naming the chunks that triggered the split.

#### 2.3 Tests

In `tests/test_chunk_topo.py` (extend):

- `test_overlapping_paths_auto_serialize`: two chunks, same wave by dependencies, overlapping paths → split into consecutive sub-waves.
- `test_disjoint_paths_stay_parallel`: two chunks, same wave, disjoint paths → remain in one wave (regression).
- `test_three_way_overlap`: three chunks with pairwise-overlapping paths → produces 3 serialized sub-waves.
- `test_overlap_ordering_is_alphabetical`: deterministic split order.

### Item 3 — Per-chunk gate arg overrides (F3 + F12)

#### 3.1 `schemas/chunks.schema.json` change

Add optional `gate_overrides` field per chunk item:

```json
"gate_overrides": {
  "type": "object",
  "additionalProperties": {
    "type": "object",
    "properties": {
      "args": {"type": "array", "items": {"type": "string"}}
    }
  },
  "description": "Per-gate argument overrides scoped to this chunk. Keys are gate ids; values override that gate's `args` when running for this chunk. Other gate fields (type, env, timeout, etc.) are unchanged."
}
```

Example usage:

```yaml
chunks:
  - id: py_db
    gate_ids: [lint, pytest_chunk]
    gate_overrides:
      pytest_chunk: {args: ["tests/test_py_db.py"]}
      lint: {args: ["check", "src/taskbridge/db.py", "tests/test_py_db.py"]}
```

#### 3.2 `skills/loop/SKILL.md` update

Add to the Setup section (step 3):

> **3.1 Apply per-chunk gate overrides.** If the chunk has `gate_overrides:`, merge into the criteria subset before invoking the adapter: for each gate in `chunk.gate_ids`, if that gate's id appears in `chunk.gate_overrides`, replace the gate's `args` with the override value. Other gate fields (type, env, timeout) come from `criteria.yaml` unchanged.

#### 3.3 `skills/plan/SKILL.md` update

In step 4 (chunk decomposition), add a bullet:

> - **Propose `gate_overrides:` for common narrowing patterns.** When a chunk owns a test file matching `tests/test_<chunk_id>.py` or a source subdirectory predictable from the chunk's `paths:`, propose a `gate_overrides` entry. This prevents sibling-in-flight test failures in parallel waves. Example: `gate_overrides: {pytest_chunk: {args: ["tests/test_<chunk_id>.py"]}}`.

#### 3.4 Tests

In `tests/test_schemas.py`:

- `test_chunk_with_gate_overrides_validates`
- `test_gate_overrides_args_must_be_string_array`
- `test_chunk_without_gate_overrides_validates` (back-compat)

In a new `tests/test_gate_overrides.py`:

- `test_loop_applies_gate_overrides`: fixture chunk with override; verify the criteria subset passed to measure_python.py reflects the override.
- `test_missing_override_falls_through_to_criteria`: no override → default criteria args.

### Item 4 — Blueprint slicing (F7)

**This is the biggest item. Been deferred since v0.2.**

#### 4.1 New helper: `scripts/blueprint_slice.py`

Public surface:

```python
def slice_blueprint(blueprint_md: str, chunk_id: str) -> str:
    """Return a sliced view of the blueprint for a single chunk:
    - The content under `## Architecture overview` (always)
    - The content under `## Cross-chunk types` (always, when present)
    - The content under `## <chunk_id>`

    Section boundaries are detected by H2 markdown headings (`^## `).
    Returns a single markdown string with section headings preserved.

    Raises ValueError if no `## <chunk_id>` section exists.
    Logs a warning (stderr) if `## Cross-chunk types` is absent.
    Falls back to returning the whole blueprint if no H2 headings exist
    (legacy / minimal blueprints).
    """
```

CLI:

```
python scripts/blueprint_slice.py --blueprint <path> --chunk-id <id>
```

Prints the sliced content to stdout.

#### 4.2 `skills/build/SKILL.md` update

Step 3b (subagent prompt construction) changes to:

> - **Sliced blueprint for the chunk** (new in v0.8). Invoke the slicer:
>   ```
>   python <plugin-root>/scripts/blueprint_slice.py \
>     --blueprint .skillgoid/blueprint.md \
>     --chunk-id <chunk_id>
>   ```
>   Pass the sliced output as the "Blueprint (relevant)" section of the subagent prompt. Subagents no longer receive the full blueprint — they receive their section + the architecture overview + the cross-chunk types section.
> - The chunk entry as YAML (id, description, gate_ids, language, depends_on, paths, gate_overrides). Gate_overrides passed through to the subagent so it can build the correct criteria subset.

Previous behavior (full-blueprint-verbatim) is gone. Projects whose blueprint has no `## <chunk_id>` section (shouldn't exist per v0.2's heading discipline, but might in legacy projects) get the full-blueprint fallback per the helper's graceful-degradation behavior.

#### 4.3 Tests

In `tests/test_blueprint_slice.py`:

- `test_slice_returns_chunk_section`: blueprint with 5 chunks, slice for chunk_id `parser` returns arch overview + parser section only.
- `test_slice_includes_cross_chunk_types_when_present`
- `test_slice_warns_when_cross_chunk_types_missing`: stderr mentions missing section.
- `test_slice_raises_for_unknown_chunk_id`
- `test_legacy_blueprint_no_h2_returns_full_content`: warning logged; caller gets full blueprint.
- `test_chunk_id_with_hyphen`: `special-forms` section matches heading `## special-forms`.
- `test_chunk_section_boundary_is_next_h2`: content up to but not including the next `## ` heading.

### Item 5 — Cross-chunk types convention (F6)

#### 5.1 Blueprint convention

Add a new authoritative section to the blueprint, immediately after `## Architecture overview`:

```markdown
## Cross-chunk types

Types that multiple chunks consume. All chunks MUST import these from the listed module rather than re-defining them locally. Changes to any type declaration here require coordinated changes to every consuming chunk.

- `Nil` (sentinel) — defined in `src/minischeme/values.py`. Import: `from minischeme.values import Nil`.
- `SExpr` (ADT: Atom, Symbol, Pair, Nil) — defined in `src/minischeme/parser.py`. Import the variant constructors from there.
- `Environment` — defined in `src/minischeme/environment.py`.
- `Token` + `TokenType` — defined in `src/minischeme/lexer.py`.

Do not re-define these types in any other module.
```

#### 5.2 `skills/plan/SKILL.md` update

Step 3 (blueprint writing) gains a mandatory bullet:

> - **Include a `## Cross-chunk types` section** immediately after `## Architecture overview`. This is an authoritative declaration of types that multiple chunks consume, along with the canonical module each lives in. The section instructs subagents to import these types rather than re-define. Omitting this section is not an error, but it means type-identity divergence (like the dual-Nil case from the minischeme stress run) will silently go undetected.

#### 5.3 `scripts/blueprint_slice.py` integration

Already handled in Item 4's helper design: the slicer always includes this section in every subagent's prompt when present.

#### 5.4 Tests

No code-level test — this is a convention, not a feature. Validation happens through:
- Documentation in `skills/plan/SKILL.md`.
- The slicer's warning when the section is absent.
- Absence of dual-type-identity findings in future stress runs.

### Item 6 — Formally close plan-refinement-mid-build

#### 6.1 `docs/roadmap.md` update

Move plan-refinement-mid-build from "Deferred — await qualitatively different project shapes" to a new section `## Formally closed (sufficient evidence)`:

```markdown
## Formally closed (sufficient evidence)

- **Plan refinement mid-build.** Zero evidence across 8 real runs (jyctl, taskq, mdstats, indexgrep, findings, taskbridge polyglot, minischeme 18-chunk stress, plus the v0.6 ship-less decision point). The minischeme run was the canonical case where plan refinement "should" have been needed — compiler-style project with mid-build IR shape discovery — and it wasn't. Not reopening without qualitatively new evidence.
```

## Repo layout changes

```
skillgoid-plugin/
├── scripts/
│   ├── validate_iteration.py         # NEW: schema validation helper
│   ├── blueprint_slice.py            # NEW: chunk-aware blueprint slicer
│   ├── chunk_topo.py                 # MODIFIED: overlap auto-serialize
│   ├── git_iter_commit.py            # MODIFIED: validate before commit
│   └── (others unchanged)
├── skills/
│   ├── build/SKILL.md                # MODIFIED: sliced blueprint in subagent prompt
│   ├── loop/SKILL.md                 # MODIFIED: apply gate_overrides
│   ├── plan/SKILL.md                 # MODIFIED: 3 new prose additions (types section, overrides, overlap warning)
│   └── (others unchanged)
├── schemas/
│   └── chunks.schema.json            # MODIFIED: gate_overrides field
├── tests/
│   ├── test_validate_iteration.py    # NEW
│   ├── test_blueprint_slice.py       # NEW
│   ├── test_gate_overrides.py        # NEW
│   ├── test_chunk_topo.py            # MODIFIED: 4 overlap tests
│   ├── test_schemas.py               # MODIFIED: 3 gate_overrides tests
│   ├── test_git_iter_commit.py       # MODIFIED: 2 validation tests
│   └── test_v08_bundle.py            # NEW: integration test exercising all items
├── docs/roadmap.md                   # MODIFIED: v0.8 shipped, plan-refinement closed, v0.9 intake
├── README.md                         # MODIFIED: "What's new in v0.8"
├── CHANGELOG.md                      # MODIFIED: [0.8.0] entry
└── .claude-plugin/plugin.json        # MODIFIED: version 0.7.0 → 0.8.0
```

Estimated new tests: ~20. Current suite 134 → ~154.

## Integration test

`tests/test_v08_bundle.py` exercises the full pipeline under one fixture. Synthetic 3-chunk project:

- chunk A: owns `shared.py`, tests at `tests/test_a.py`
- chunk B: owns `shared.py` AND `b.py`, tests at `tests/test_b.py` (DELIBERATE overlap with A)
- chunk C: owns `c.py`, tests at `tests/test_c.py`, no overlap

Assertions:
1. `chunk_topo.plan_waves` splits [A, B, C] into two waves: [[A, C], [B]] because A and B overlap on shared.py.
2. Feed a malformed iteration JSON (`status` instead of `exit_reason`) to `git_iter_commit.py`; assert exit 2 + stderr message.
3. `blueprint_slice.py` returns A's section + architecture overview + cross-chunk-types section for `chunk-id=A`; does NOT include B's or C's sections.
4. Loop skill's gate_overrides merging: chunk A with `gate_overrides: {pytest_chunk: {args: ["tests/test_a.py"]}}` → criteria subset has narrowed args; chunk without overrides → unchanged.

Runs end-to-end; validates the v0.8 machinery composes correctly.

## Backward compatibility

All additions are opt-in. Existing v0.7 projects work unchanged:

| Change | v0.7 project behavior | v0.8 project behavior |
|---|---|---|
| gate_overrides field | absent → criteria defaults apply (unchanged) | present → overrides apply |
| paths overlap serialization | chunks without paths: → no change (v0.7 fallback to `git add -A`) | chunks with paths: → auto-split applies |
| Blueprint slicer | blueprint with no `## <chunk_id>` headings → full blueprint passed (warning) | blueprint with proper headings → sliced view |
| Cross-chunk types section | absent → slicer warns but proceeds | present → always included |
| Iteration schema validation | valid v0.7 iterations → pass | invalid v0.7 iterations (rare silent-corruption cases) → now refuse commit |

One user-visible migration risk: projects with historical iteration JSONs that were silently-schema-non-conforming will now fail on resume. Mitigation: CHANGELOG documents the migration; `validate_iteration.py` as a standalone tool lets users find bad records beforehand; v0.7 iterations passed validation at time-of-write since the schema is additionally permissive (`additionalProperties: true`).

## Vault updates

Performed by `retrospect` on the first v0.8 real run, NOT by v0.8 itself. Candidates derived from the minischeme stress findings:

- **New lesson:** "Blueprint must declare a `## Cross-chunk types` section for multi-chunk type contracts to hold." (from F6)
- **New lesson:** "Chunks modifying the same file should not parallelize in the same wave — chunk_topo auto-splits them, but the blueprint is cleaner with explicit depends_on." (from F8)
- **New lesson:** "Iteration JSONs are now schema-validated before commit. Subagents writing records must exactly match `schemas/iterations.schema.json` field names." (from F9)
- **New lesson:** "Per-chunk gate_overrides prevent parallel-wave test/lint interference. Propose them in chunks.yaml rather than hoping subagents narrow at measure time." (from F3/F12)

## Docs

- **README.md "What's new in v0.8" section:** 5 bullets, following the v0.7 style.
- **CHANGELOG.md `[0.8.0]` entry:** enumerates each Changed/Added item + the one Back-Incompat note (iteration schema validation now enforced).
- **docs/roadmap.md:** v0.8 shipped; plan-refinement-mid-build moved to "Formally closed"; v0.9 intake notes call out polyglot still waiting, and the deferred items (F10 out-of-pipeline, F11 double-commit, F7's per-chunk blueprint-files alternative approach if evidence demands).

## Release sequence

1. Land v0.8 spec + plan in repo (this doc + its companion plan).
2. Implement all 5 items in a single PR (shared test scaffolding via `test_v08_bundle.py`).
3. Re-run a minischeme-style verification to confirm F5/F6/F7/F8/F9 close.
4. Update README/roadmap/CHANGELOG/plugin.json version bump to 0.8.0.
5. Ship.

Estimated effort: ~8-10 days of focused work.

## Explicit non-priorities with evidence criteria

Same discipline as v0.7's spec — state what's deferred and what evidence would re-open it.

- **Polyglot language support (languages[], node-gates, polyglot clarify defaults, multi-language vault):** waits on 2-3 organic polyglot runs, NOT synthetic stress tests. One data point (taskbridge) isn't enough.
- **F10 (out-of-pipeline commits by subagents fixing adjacent chunks' tests):** real but requires more evidence about how cross-chunk fixups should be handled. Re-open if 2+ future runs show the pattern.
- **F11 (double-commit symptom):** should be incidentally addressed by F9's schema validation. If it recurs after v0.8, investigate as a separate issue.
- **Glob-aware paths overlap detection:** v0.8 uses exact-string match. If a run shows chunks declaring overlapping globs (`src/*.py` vs `src/**/*.py`) that the exact-string matcher misses, add glob-aware matching in v0.9.
- **Per-chunk blueprint files (alternative to in-memory slicing):** v0.8 goes with in-memory. If v0.9 evidence shows users want on-disk per-chunk blueprints for audit or manual editing, revisit.
- **Dashboards, rehearsal mode, gate-type plugins:** unchanged from v0.7's deferred list — no new evidence.

## Risk acknowledgment

Biggest risk: the item list is larger than any prior release. v0.7 shipped 2 items in ~1 week; v0.8 ships 5 items aiming for ~8-10 days. Mitigation:

- Four of five items are small-to-medium (F5/F9, F3/F12, F6, F8). F7 blueprint slicing is the only architectural add.
- Integration test (`test_v08_bundle.py`) exercises all items together early, catching composition issues before PR-close.
- Fully back-compat: no coordinated migration for existing v0.7 projects.

Secondary risk: F7's in-memory slicing approach may not be what downstream tools want. If someone wants to debug a sliced blueprint, they can invoke the CLI directly (`python scripts/blueprint_slice.py --chunk-id foo`); we're not hiding the slice behind opaque internal state.
