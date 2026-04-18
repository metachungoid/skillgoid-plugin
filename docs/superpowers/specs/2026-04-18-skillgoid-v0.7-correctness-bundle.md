# Skillgoid v0.7 — Correctness Bundle

**Status:** spec
**Date:** 2026-04-18
**Predecessor:** v0.6 Shell-String Python Resolution (shipped same day)
**Evidence source:** `taskbridge` polyglot stress run, 2026-04-18 (findings doc: `~/Development/skillgoid-test/v0.7-findings.md`, retrospective: `~/Development/skillgoid-test/taskbridge/.skillgoid/retrospective.md`)

## Context

v0.6 shipped `$SKILLGOID_PYTHON` export as a one-item release. The roadmap's "How to pick up v0.7" section prescribed: *"Run Skillgoid on a qualitatively different project shape... observe what actually fails... spec v0.7 around the top 1-2 observed issues."*

A polyglot (Python + TypeScript) stress run, executed by a driver session manually interpreting the SKILL.md files, surfaced 28 findings across 3 severity tiers. Two of those findings are production-correctness bugs that must not ship into another release:

- **v0.5's parallel-wave feature silently corrupts git history.** In a real parallel dispatch of two wave-1 subagents (`py_db` + `ts_db`), the ts_db commit labeled "iter 1 of chunk ts_db" swept up py_db's in-progress files because `git_iter_commit.py` uses `git add -A`. The iteration-filename race (both subagents naturally target `001.json`) is also real — it failed to fire only by temporal luck.
- **Gate `env:` is honored by 2 of 7 gate types.** `pytest`, `import-clean`, and `coverage` hardcode `PYTHONPATH=<project>/src` and silently ignore the gate's `env:` field. `ruff` and `mypy` don't accept env at all. Prior single-language runs coincidentally used `<project>/src/` layouts, masking the bug. The first polyglot project (with source at `py/src/`) tripped it immediately on 3 of 4 Python gates.

One closely-related smaller finding is folded in because it touches the same code:
- **`git_iter_commit.py --iteration` accepts a relative path but doesn't resolve it against `--project`.** Invocations with the documented relative form silently noop on soft-fail. Every subagent-dispatched loop is at risk.

A fourth finding is resolved by documentation alone, no code:
- **Coverage gates in per-chunk `gate_ids` produce false-positive failures** until the last chunk touching the package lands. They belong in `integration_gates`. `clarify` prose doesn't currently say that.

Everything else in the 28-finding set — polyglot defaults, `languages[]` migration, `node-gates` adapter, multi-language vault, structured-hint parity — is deferred to v0.8+. One polyglot run is not enough evidence to commit to a full polyglot design. Fix the correctness leaks, keep observing, spec v0.8 against 2-3 more polyglot data points.

## Goals

1. Make v0.5's parallel-wave dispatch produce correct per-chunk git history, with no filename race.
2. Make gate `env:` work uniformly across all gate types so polyglot (and any non-standard-layout) projects work without `run-command` shims.
3. Fold in the small, related correctness fix in `git_iter_commit.py` path handling.
4. Update `clarify` prose to steer users away from the per-chunk-coverage trap.

## Non-goals

The following findings are deliberately excluded from v0.7:

- `language` → `languages[]` schema migration (`criteria.yaml` top-level language stays single-string).
- Polyglot-aware defaults in `clarify` (Python-only defaults stay).
- TS/Node/etc. gate types in `schemas/criteria.schema.json` — run-command stays the polyglot escape hatch.
- Multi-language vault (`<language>-lessons.md` stays single-language).
- `metrics_append` / `stats_reader` multi-language awareness.
- `node-gates` or any other language adapter.
- Structured hint parity for `run-command` gates (generic `exit=N, expected 0` stays).
- Feasibility-phase awareness of Node tooling.

These are real gaps. They are not fixed by v0.7. Each waits on either (a) more polyglot user evidence before we commit to a shape, or (b) explicit user signal that the current escape hatch is too painful.

## Design

### Item 1 — Parallel-wave correctness

#### 1.1 Per-chunk iteration filenames

**Change:** iteration files move from `.skillgoid/iterations/NNN.json` to `.skillgoid/iterations/<chunk_id>-NNN.json`. `NNN` remains per-chunk (each chunk numbers its own iterations starting at 001, zero-padded to 3 digits).

**Rationale:** with per-chunk filename namespaces, two subagents dispatched in the same wave can never target the same filename. The filename-arbitration problem dissolves without needing a lockfile, O_EXCL primitive, or post-hoc reconciliation.

**Affected code paths:**
- `skills/loop/SKILL.md` step 8 — update the iteration-filename prose to specify `<chunk_id>-NNN.json`. Add the scratch-file-hygiene line (below).
- `hooks/gate-guard.sh` — already sorts `iterations/*.json` alphabetically and picks the last. Alphabetical sort of prefixed filenames still yields a usable "latest" (per chunk_id, last alphabetical); keep as-is for v0.7. Grouping-by-chunk-id is a v0.8 polish.
- `hooks/detect-resume.sh` — reads chunks.yaml count, not filenames; unchanged.
- `scripts/metrics_append.py` — `_load_iterations` globs `*.json`; prefixed names still match; `_outcome` groups by `chunk_id` from the record body (not filename); unchanged.
- `skills/retrospect/SKILL.md` step 1 — "Read all `.skillgoid/iterations/*.json` in order" — still works; update prose to note files are prefixed by chunk_id but order by filename (which equals chunk_id, then N) is fine for retrospect's purposes.

**Back-compat:** existing v0.6 projects with `NNN.json` files still match the `*.json` glob and still parse. The two naming conventions coexist if a project is resumed across the upgrade. No migration script, no project-touching upgrade path.

#### 1.2 `paths:` field in `chunks.yaml`

**Schema change:** add optional `paths: [<glob-or-path>, ...]` to each chunk entry in `schemas/chunks.schema.json`. Items are strings; interpretation is "paths or globs, relative to project root." Example:

```yaml
chunks:
  - id: py_db
    language: python
    paths:
      - "py/src/taskbridge/db.py"
      - "py/tests/test_db.py"
    gate_ids: [py_lint, py_test, py_cov, py_import]
    depends_on: [scaffold]
```

**Semantics:** `paths:` declares which project paths this chunk owns for commit-scoping. It does NOT restrict what files the chunk subagent may write — it only bounds what `git_iter_commit.py` stages into the chunk's commit.

**`skills/plan/SKILL.md` update:** step 4 gains a bullet: *"For each chunk, declare `paths: [...]` listing the project paths the chunk owns. Use specific paths when possible; directory globs (`py/src/taskbridge/db.*`) are acceptable. Chunks in the same wave should have non-overlapping `paths:`."*

**`skills/build/SKILL.md` step 3b update:** include the chunk's `paths:` list in the subagent prompt's chunk yaml block so the subagent knows its scope.

#### 1.3 `scripts/git_iter_commit.py` rewrite

**New invocation contract:**

```
python git_iter_commit.py \
  --project <absolute-or-relative-project-path> \
  --iteration <path-to-iteration.json> \
  --chunks-file <path-to-chunks.yaml>
```

Where:
- `--project` resolves to absolute via `.resolve()` (unchanged).
- `--iteration` — if relative, is now resolved against `--project` (F25 fix). Must exist and be readable.
- `--chunks-file` — new required flag. Path to `chunks.yaml` (usually `<project>/.skillgoid/chunks.yaml`). Also resolved against `--project` if relative.

**Behavior changes:**

1. **Hard-fail on unreadable iteration JSON** (replaces the soft-fail that previously silently skipped the commit). Print `git_iter_commit: cannot read iteration at <path>: <error>` to stderr, exit 2. The loop skill's caller is responsible for handling; previously a silent skip hid missed commits.
2. **Scoped `git add`.** Read `chunks.yaml`; look up the chunk whose `id` matches the iteration record's `chunk_id`. If that chunk has a `paths:` list, stage those paths plus the iteration file:
   ```
   git add <paths-from-chunks.yaml>... <iteration-file>
   ```
3. **Fallback with warning.** If the chunk has no `paths:` declared (existing v0.6 projects upgrading), emit to stderr: `git_iter_commit: chunk <id> has no paths: declared, falling back to 'git add -A' — consider adding paths: for safer parallel waves` and proceed with the old `git add -A` behavior. Exit 0 on success. This preserves v0.6 single-chunk-wave behavior identically.
4. **Non-git projects:** unchanged — return 0 with no commit (documented noop).

**Commit message:** unchanged structure. `_build_message` continues to produce `skillgoid: iter N of chunk <id> (<status>)`.

#### 1.4 Scratch-file hygiene

**`skills/loop/SKILL.md` step 8 update:** add one paragraph:

> **Scratch files.** Any temp files you create (including the one used to pass `gate_report` to `stall_check.py`) must live under `tempfile.mkdtemp()` or `$TMPDIR`, never inside the project tree. If a scratch file lands in the project, `git_iter_commit.py`'s staging will sweep it into the iteration commit.

**`skills/clarify/SKILL.md` step 5.3 update:** the default Python `.gitignore` template gains one line:

```
/tmp*.json
```

A belt-and-suspenders guard against scratch files that slip the loop skill's guidance. Documented in the step's rationale paragraph as such.

### Item 2 — Gate `env:` honored uniformly

#### 2.1 `scripts/measure_python.py` handler changes

Extract the existing `_merge_env(project, gate_env)` helper usage into every gate handler. The current `_merge_env` (line 51) already correctly merges `os.environ`, the `SKILLGOID_PYTHON` export, and the gate's `env:` field with gate `env:` winning — it is the target shape; the other handlers just don't call it.

**Per-handler changes:**

- **`_gate_pytest`** (line 122): replace hardcoded `env = {**os.environ, "PYTHONPATH": str(project/"src") + ...}` with:
  ```python
  env = _merge_env(project, gate.get("env") or {})
  if "PYTHONPATH" not in (gate.get("env") or {}):
      existing = env.get("PYTHONPATH", "")
      env["PYTHONPATH"] = str(project / "src") + (os.pathsep + existing if existing else "")
  ```
  i.e., merge first; inject `<project>/src` as PYTHONPATH default only when the user didn't supply one. Preserves v0.6 behavior for projects that omit env; unblocks non-standard-layout projects that supply env.

- **`_gate_import_clean`** (line 204): same pattern.
- **`_gate_coverage`** (line 281): same pattern.
- **`_gate_ruff`** (line 148): add `env = _merge_env(project, gate.get("env") or {})` and pass `env=env` to `subprocess.run`. No default keys injected — ruff didn't have env before; gate `env:` is additive-only.
- **`_gate_mypy`** (line 176): same as ruff.

**Default-preservation rule stated plainly:** for handlers that currently inject `PYTHONPATH=<project>/src` as part of their own logic (pytest, import-clean, coverage), the injection is preserved *only when the user's gate `env:` does not specify a `PYTHONPATH`*. User-supplied `env: {PYTHONPATH: ...}` wins cleanly. This is the least-surprising backward-compat behavior.

#### 2.2 Coverage-scope prose change (F28)

No code change. `skills/clarify/SKILL.md` step 5.2 currently proposes `coverage` as a gate inside `gates:` (and implicitly as a member of each chunk's `gate_ids`). Replace with:

> **5.2 Default coverage gate for Python projects.** Propose a `coverage` entry under `integration_gates:`, not inside `gates:`. Rationale: coverage is a whole-package metric. If coverage lives inside `gates:` and chunks reference it via `gate_ids`, it will fail false-positive on every chunk until the last chunk touching the package lands — producing iteration-budget churn for no fault of the chunk being evaluated. Moving it to `integration_gates` runs it once after all chunks pass, which is the semantic shape that matches the metric.
>
> Example:
> ```yaml
> integration_gates:
>   - id: cov
>     type: coverage
>     target: "<package-name>"
>     min_percent: 80
>     compare_to_baseline: false
> ```
>
> Existing projects with `coverage` in `gates:` continue to work (no schema change). The recommendation applies only to freshly proposed criteria.yaml.

The subprocess-coverage caveat paragraph (about pytest-cov not instrumenting subprocess calls) stays exactly where it is.

### Integration with existing infrastructure

- **`skills/build/SKILL.md`:** step 3b's subagent-prompt template picks up the chunk's `paths:` field automatically when the chunk entry is included as YAML. No structural change to build.
- **`skills/python-gates/SKILL.md`:** add one sentence to the `env:` note: *"All gate types now honor `env:`; previously only `run-command` and `cli-command-runs` did. Polyglot and non-standard layouts can use `env: {PYTHONPATH: ...}` on pytest/coverage/import-clean gates."*
- **`skills/unstick/SKILL.md`:** needs to know the iteration-filename convention changed (reads the latest iteration for a chunk). Step 2 — update the path pattern from `iterations/NNN.json` to `iterations/<chunk_id>-NNN.json` when locating the chunk's latest iteration.
- **`schemas/iterations.schema.json`:** no change. Filenames aren't schema-validated.
- **Metrics / stats:** no change. Record schema is identical; filenames don't enter metrics output.

## Testing strategy

### New tests

- **`tests/test_git_iter_commit.py` — new cases:**
  - `test_iteration_relative_path_resolves_against_project` — pass `--iteration .skillgoid/iterations/scaffold-001.json` with a relative path; assert the commit succeeds when called from arbitrary cwd.
  - `test_iteration_unreadable_hard_fails` — non-existent file → exit 2, stderr mentions the path.
  - `test_paths_scopes_git_add` — fixture project with two chunks writing overlapping work; commit for chunk A with `paths:` scoped to A's files; assert chunk B's files are NOT in the commit.
  - `test_missing_paths_falls_back_to_add_all_with_warning` — chunk has no `paths:`; commit still works via `-A`; stderr contains the documented warning string.

- **`tests/test_env_gate.py` — parametrized new tests (one per gate type):**
  - `test_pytest_honors_env_pythonpath` — gate with `env: {PYTHONPATH: custom/src}`; assert the pytest subprocess sees that value (via a test that inspects `os.environ["PYTHONPATH"]` inside the collected test).
  - `test_pytest_default_pythonpath_when_env_absent` — no env; assert `<project>/src` is still prepended.
  - `test_import_clean_honors_env_pythonpath` — same pattern.
  - `test_coverage_honors_env_pythonpath` — same pattern.
  - `test_ruff_honors_env` — ruff with `env: {RUFF_CACHE_DIR: ...}`; assert subprocess sees it.
  - `test_mypy_honors_env` — mypy with arbitrary env key; assert subprocess sees it.

- **`tests/test_parallel_wave_commit.py` — new file:** spawn two `git_iter_commit.py` processes concurrently (via `subprocess.Popen`), each writing its own iteration + committing its chunk's `paths:` only. Assert:
  - Both commits land.
  - Each commit's `git show --name-only` contains only its chunk's files plus its own iteration JSON.
  - No file appears in two commits.

- **`tests/test_iteration_filename_backcompat.py` — new file:** fixture iterations dir mixing `old-style-NNN.json` and `<chunk_id>-NNN.json`; assert `metrics_append.build_metrics_line` and the gate-guard chunk-count logic both process correctly.

### Existing-test regressions

Run the full suite against v0.7 changes. Any existing test that relied on `git add -A` behavior gets updated to declare `paths:` explicitly; those that don't test commit scoping stay unchanged.

### Manual validation

Re-run the `taskbridge` polyglot stress scenario under v0.7:
- Scaffold gates should pass (unchanged).
- Wave 1 parallel dispatch: verify iteration files are `py_db-001.json` and `ts_db-001.json`. Verify each chunk's commit contains only its own files (no cross-contamination). Verify no `tmp*.json` in any commit.
- py_db's pytest/import-clean/coverage gates should now succeed under the correct `env: {PYTHONPATH: py/src}` (subject to actual coverage levels — expect py_cov to fail only for F28 reasons, not F17 reasons).

## Vault & documentation

### Vault updates (performed by `retrospect` on the first v0.7 real run, not by v0.7 itself)

- **Rewrite lesson** *"`cli-command-runs` does not pass PYTHONPATH through"* (currently `Status: resolved in v0.4`): broaden title and body to cover all gate types, change status to `resolved in v0.7`.
- **New lesson** *"Coverage belongs in integration_gates, not per-chunk gate_ids"* — derived from the F28 observation.
- **New lesson** *"Parallel waves require `paths:` per chunk for correct per-chunk git history"* — derived from F26.

### Plugin docs

- **`README.md` "What's new in v0.7" section:** two bullets, following the style of prior versions.
  - Parallel-wave correctness: per-chunk iteration filenames + `paths:` scoped commits.
  - Gate `env:` honored universally.
- **`docs/roadmap.md`:** v0.7 entry added to `## Shipped`. "How to pick up v0.8" section gains a new note: *"Polyglot language-support shape (languages[] migration, polyglot clarify defaults, node-gates adapter) waits on 2-3 more polyglot projects before committing to the design."*
- **`CHANGELOG.md`:** standard entry with migration guidance (there is none required — everything is back-compat).

### Spec + plan references

Add spec reference to `docs/roadmap.md` in the v0.7 entry: `Spec: docs/superpowers/specs/2026-04-18-skillgoid-v0.7-correctness-bundle.md`.

## Deferred items — explicit non-priorities with rationale

For each item, state the evidence required to pick it back up:

- **`languages[]` migration + polyglot-aware `retrieve`/`clarify`/`retrospect`:** pick up when a second polyglot project produces a different shape (e.g., Python + Go instead of Python + TS). Evidence of design-space variation is required before committing to a schema.
- **`node-gates` adapter + TS gate-type enum in schema:** pick up when a user reports the `run-command` escape hatch has produced a concrete pain point (e.g., a parsing-quality regression in a repeat-iteration, not just "hints are generic").
- **Polyglot feasibility checks:** pick up with `node-gates` — feasibility checks per language adapter is one unit of work.
- **Multi-language vault / multi-language metrics:** pick up alongside `languages[]`. Same migration surface.
- **Plan refinement mid-build, rehearsal mode, unstick, dashboards:** zero evidence after 6 real runs + the stress run. Keep deferred. Roadmap already flagged these; v0.7 re-affirms.

## Release sequence

1. Land v0.7 spec + plan in repo (this doc + its companion plan).
2. Implement items 1 and 2 in a single PR (they share test scaffolding).
3. Run the taskbridge re-verification scenario manually; confirm F17/F22/F26 evidence closes.
4. Update README/roadmap/CHANGELOG/plugin.json version bump to 0.7.0.
5. Ship.

Total estimated effort: ~1 week of focused work.
