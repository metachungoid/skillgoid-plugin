# Skillgoid v0.9 Recovery Stress-Test Execution Plan — `chrondel`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note:** This is an *experiment-execution plan*, not a feature-implementation plan. Tasks include scripted interventions (file reverts, process kills, manual unstick invocations) at specific pipeline moments. The outputs are findings + retrospective, not shipped features. v0.9's feature spec will be written AFTER this experiment.

**Goal:** Run Skillgoid v0.8 against `chrondel` (a date/time library with deliberately-strict acceptance) while injecting 8 scripted intervention scenarios to exercise the stall/unstick/budget/resume/gate-guard/integration-retry/retrospect-only machinery that has zero prior data across 8 real runs.

**Architecture:** Same driver pattern as minischeme (this Claude session manually interprets `skills/*/SKILL.md` and dispatches parallel-wave subagents via `Agent` tool). New for this experiment: out-of-band interventions between subagent dispatches — file reverts, `max_attempts` tightening, process kills, hint injections. A multi-session gap is required to legitimately exercise SessionStart resume.

**Tech Stack:** Python 3.11+ (stdlib only for chrondel runtime); plugin venv for `measure_python.py` + helpers.

**Spec:** `docs/superpowers/specs/2026-04-18-skillgoid-v0.9-recovery-stress-test-design.md` (commit `da28af0`).

**Evidence target:** Append findings to `~/Development/skillgoid-test/v0.9-findings.md`. Confirm or falsify hypotheses H1–H10 listed in the spec.

---

## Working layout

```
~/Development/skillgoid-test/
├── v0.9-findings.md                ← append-only findings (created Task 1)
├── chrondel/                       ← project tree (created Task 1)
│   ├── .skillgoid/
│   │   ├── goal.md                 ← Task 2
│   │   ├── criteria.yaml           ← Task 2 (strict acceptance)
│   │   ├── blueprint.md            ← Task 4
│   │   ├── chunks.yaml             ← Task 4
│   │   ├── iterations/             ← Tasks 5-17 (subagents)
│   │   └── retrospective.md        ← Task 18
│   ├── src/chrondel/               ← created chunk-by-chunk
│   ├── tests/
│   └── pyproject.toml              ← Task 5
└── (other test projects unchanged)
```

---

## Reusable chunk-subagent prompt template

Same shape as v0.8 stress-test plan. Placeholders filled per dispatch. Defined once here.

```
You are a Skillgoid chunk subagent executing ONE ITERATION of chunk `<CHUNK_ID>` for the chrondel v0.9 recovery stress-test. This is a v0.9-evidence experiment — DO NOT loop or retry on gate failure unless the driver explicitly asks. Do the iteration once, write the iteration JSON, commit, return.

## Context
- Project dir: /home/flip/Development/skillgoid-test/chrondel
- Plugin dir: /home/flip/Development/skillgoid/skillgoid-plugin
- Plugin venv python: /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python
- v0.8 conventions apply: iteration files named `<chunk_id>-NNN.json`; git_iter_commit takes --chunks-file; per-chunk `paths:` declared; `gate_overrides:` supported; blueprint slicer passes only your section.

## Your chunk (verbatim from chunks.yaml)
<PASTE_CHUNK_YAML_BLOCK>

## Sliced blueprint (from scripts/blueprint_slice.py)
<PASTE_SLICED_BLUEPRINT>

## Past lessons summary
<PASTE_RETRIEVE_SUMMARY>

## Prior iterations for this chunk (if resuming; max 2)
<PASTE_PRIOR_ITER_RECORDS>

## Build step
Implement the chunk per blueprint. Strict acceptance — first-iteration bugs on DST/leap-year/timezone/format-round-trip are EXPECTED; that's the point of the experiment.

## Measure step
Build /tmp/<chunk_id>_criteria.yaml with the subset of gates your chunk cares about (applying any chunk.gate_overrides). Invoke:
  /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
    /home/flip/Development/skillgoid/skillgoid-plugin/scripts/measure_python.py \
    --project /home/flip/Development/skillgoid-test/chrondel \
    --criteria-stdin < /tmp/<chunk_id>_criteria.yaml

## Reflect step
Write `.skillgoid/iterations/<chunk_id>-NNN.json`. v0.8 schema validation is ACTIVE; iteration: N as integer; include all required fields (iteration, chunk_id, gate_report) plus started_at, ended_at, gates_run, reflection, notable, failure_signature, exit_reason.

Compute failure_signature: write gate_report to a tempfile.gettempdir() tmp file, run stall_check.py, use the 16-char hex.

## Git commit step
  /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
    /home/flip/Development/skillgoid/skillgoid-plugin/scripts/git_iter_commit.py \
    --project /home/flip/Development/skillgoid-test/chrondel \
    --iteration .skillgoid/iterations/<chunk_id>-NNN.json \
    --chunks-file .skillgoid/chunks.yaml

If git_iter_commit exits 2 (schema validation failure), INSPECT your iteration JSON against schemas/iterations.schema.json and fix before proceeding. v0.8 behavior is correct — don't work around it.

## Scratch hygiene
All temp files under tempfile.gettempdir(). NEVER in the project tree.

## Return format
Standard JSON: chunk_id, iteration_file, gate_report_passed, failing_gates, exit_reason, commit_sha, files_in_commit, v0_9_friction_observations, race_evidence (if parallel wave).
```

---

## Task 1: Project + findings setup

**Files:**
- Create: `/home/flip/Development/skillgoid-test/chrondel/`
- Create: `/home/flip/Development/skillgoid-test/chrondel/.gitignore`
- Create: `/home/flip/Development/skillgoid-test/v0.9-findings.md`

- [ ] **Step 1.1: Verify v0.8 baseline + plugin venv**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
. .venv/bin/activate
pytest -q 2>&1 | tail -1
ruff check . 2>&1 | tail -1
git log --oneline -1
```
Expected: 169 tests pass, ruff clean, latest commit is the v0.8 merge or later.

- [ ] **Step 1.2: Create project tree**

```bash
mkdir -p /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations
mkdir -p /home/flip/Development/skillgoid-test/chrondel/.skillgoid/integration
cd /home/flip/Development/skillgoid-test/chrondel
git init -q
```

- [ ] **Step 1.3: Write `.gitignore`**

```bash
cat > /home/flip/Development/skillgoid-test/chrondel/.gitignore <<'EOF'
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
.venv/
*.egg-info/
build/
dist/
/tmp*.json
EOF
```

- [ ] **Step 1.4: Initialize findings log**

Create `/home/flip/Development/skillgoid-test/v0.9-findings.md`:

```markdown
# Skillgoid v0.9 findings — chrondel recovery stress run

Running date: 2026-04-18
Target: `~/Development/skillgoid-test/chrondel/` — date/time library with strict acceptance, 8 scripted intervention scenarios
Skillgoid version under test: v0.8 (tag v0.8.0, commit f5fc0bc)
Driver: Claude (Opus 4.7) manually interpreting `skills/*/SKILL.md`
Spec: `~/Development/skillgoid/skillgoid-plugin/docs/superpowers/specs/2026-04-18-skillgoid-v0.9-recovery-stress-test-design.md`

## Hypotheses tracker

| # | Hypothesis | Status |
|---|---|---|
| H1 | Organic multi-iteration works | pending |
| H2 | stalled exit fires on repeated failure_signature | pending |
| H3 | /skillgoid:unstick unblocks a stalled chunk | pending |
| H4 | budget_exhausted fires cleanly at max_attempts | pending |
| H5 | SessionStart hook emits resume context | pending |
| H6 | /skillgoid:build resume picks up partial state | pending |
| H7 | gate-guard.sh blocks Stop mid-loop | pending |
| H8 | integration_retries re-dispatches with failure context | pending |
| H9 | /skillgoid:build retrospect-only finalizes stuck project | pending |
| H10 | v0.8 schema validation doesn't over-reject during recovery | pending |

## Scripted scenarios

| # | Scenario | Status |
|---|---|---|
| S1 | Organic multi-iteration (no intervention) | pending |
| S2 | Forced stall on formatter | pending |
| S3 | Unstick injection | pending |
| S4 | Budget exhaustion on intervals (max_attempts: 2) | pending |
| S5 | SessionStart resume (multi-session) | pending |
| S6 | Gate-guard Stop-block | pending |
| S7 | Integration retry loop | pending |
| S8 | retrospect-only finalization | pending |

## Findings

(Severity: 🔴 blocking, 🟡 friction, 🟢 minor)

## Phase log

(Filled in as the experiment runs.)
```

- [ ] **Step 1.5: Commit baseline**

```bash
cd /home/flip/Development/skillgoid-test/chrondel
git add .gitignore
git commit -qm "init: chrondel recovery stress-test scaffold"
```

---

## Task 2: Retrieve + Clarify

**Files:**
- Create: `.skillgoid/goal.md`
- Create: `.skillgoid/criteria.yaml` (STRICT acceptance)

- [ ] **Step 2.1: Run vault_filter for active Python lessons**

```bash
/home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
  /home/flip/Development/skillgoid/skillgoid-plugin/scripts/vault_filter.py \
  --lessons-file ~/.claude/skillgoid/vault/python-lessons.md \
  --plugin-json /home/flip/Development/skillgoid/skillgoid-plugin/.claude-plugin/plugin.json
```

Record active lessons in v0.9-findings.md phase log under "retrieve."

- [ ] **Step 2.2: Write `.skillgoid/goal.md`**

```markdown
# Goal

Build `chrondel`, a Python 3.11+ date/time library with intentionally strict behavior around timezones, DST transitions, leap handling, and format round-trips. The strictness is deliberate — it forces iteration, which is the point of this stress run.

## Scope

- Core types: `Date`, `Time`, `DateTime`, `Duration`, `Interval`, `Timezone`
- Parsing: ISO-8601, RFC-3339, and a forgiving `parse_any()` that tries multiple formats
- Formatting: strftime-compatible + ISO-8601 + custom format strings
- Arithmetic: add/subtract Durations, respecting DST transitions (wall-time semantics)
- Comparison: total ordering, with instant-vs-wall-time distinction made explicit
- Intervals: contains, overlaps, union/intersection (pairwise only)
- Timezone conversion
- CLI: `chrondel parse <str>`, `chrondel diff <a> <b>`, `chrondel convert <dt> --tz <tz>`

## Non-goals

- Calendars other than Gregorian
- Recurrence rules (RRULE)
- Historical timezone data before 1970
- Subsecond timezone offsets

## Success signals

- parse/format round-trip: `parse(format(dt)) == dt` for 500 fuzz-generated inputs
- DST wall-time semantics: adding 1 day to 2026-11-01T01:30 Los_Angeles produces 2026-11-02T01:30
- Timezone equality is instant-based via `.to_instant()`; wall-time equality is separate
- All 13 Allen relations correct for Intervals
- Leap year handled: 2000-02-29 valid, 1900-02-29 invalid
- CLI round-trips: `chrondel parse "2026-04-18" | chrondel format` emits identical output

## Constraints

- Python 3.11+, stdlib only (no arrow, pendulum, dateutil, or pytz dependencies)
- Strict acceptance criteria are intentional
```

- [ ] **Step 2.3: Write `.skillgoid/criteria.yaml`**

```yaml
language: python

loop:
  max_attempts: 5
  skip_git: false

gates:
  - id: lint
    type: ruff
    args: ["check", "src/", "tests/"]

  - id: import_clean
    type: import-clean
    module: chrondel
    env:
      PYTHONPATH: "src"

  - id: pytest_chunk
    type: pytest
    args: ["tests/"]
    env:
      PYTHONPATH: "src"

integration_gates:
  - id: cli_help
    type: cli-command-runs
    command: ["python", "-m", "chrondel", "--help"]
    expect_exit: 0
    expect_stdout_match: "usage:"
    env:
      PYTHONPATH: "src"

  - id: cli_roundtrip
    type: run-command
    command:
      - "bash"
      - "-c"
      - |
        set -euo pipefail
        OUT=$($SKILLGOID_PYTHON -m chrondel parse "2026-04-18T12:30:00Z" --format iso8601)
        [ "$OUT" = "2026-04-18T12:30:00Z" ]
    expect_exit: 0
    env:
      PYTHONPATH: "src"

  - id: cov
    type: coverage
    target: "chrondel"
    min_percent: 80
    compare_to_baseline: false

integration_retries: 2

acceptance:
  - "parse/format round-trip holds for 500 fuzz-generated DateTimes"
  - "DST-sensitive addition preserves wall time"
  - "All 13 Allen relations correct for Intervals"
  - "Leap year 2000-02-29 valid; 1900-02-29 raises"
  - "CLI parse + format round-trips losslessly"

models:
  chunk_subagent: sonnet
  integration_subagent: haiku
```

- [ ] **Step 2.4: Validate criteria.yaml**

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
cd /home/flip/Development/skillgoid-test/chrondel
python -c "
import json, yaml, jsonschema
data = yaml.safe_load(open('.skillgoid/criteria.yaml'))
schema = json.load(open('/home/flip/Development/skillgoid/skillgoid-plugin/schemas/criteria.schema.json'))
jsonschema.validate(data, schema)
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 2.5: Update findings phase log**

Append to v0.9-findings.md under Phase log:

```markdown
### retrieve
- Active vault lessons: <list>

### clarify
- goal.md + criteria.yaml written with STRICT acceptance (deliberate per spec to force iteration).
- Schema validated clean.
```

- [ ] **Step 2.6: Commit**

```bash
cd /home/flip/Development/skillgoid-test/chrondel
git add .skillgoid/goal.md .skillgoid/criteria.yaml
git commit -qm "clarify: chrondel goal + strict criteria"
```

---

## Task 3: Feasibility check

**Files:** none modified

- [ ] **Step 3.1: Verify tools**

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
which ruff pytest bash
python -m pytest --cov --version 2>&1 | head -3
```
Expected: plugin venv has ruff + pytest + pytest-cov; bash on PATH.

- [ ] **Step 3.2: Update findings phase log**

Append to v0.9-findings.md:

```markdown
### feasibility
- Plugin venv tools resolvable. bash available. PYTHONPATH=src is a relative path that scaffold creates (soft warning per v0.5 scaffolding-awareness).
- Decision: proceed.
```

No commit — feasibility is observation only.

---

## Task 4: Plan (blueprint + chunks)

**Files:**
- Create: `.skillgoid/blueprint.md`
- Create: `.skillgoid/chunks.yaml`

- [ ] **Step 4.1: Write `.skillgoid/blueprint.md`**

Write this exact content to `/home/flip/Development/skillgoid-test/chrondel/.skillgoid/blueprint.md`:

```markdown
# Blueprint — chrondel

## Architecture overview

A pure-stdlib date/time library with strict semantics. The pipeline is:

1. **core_types** defines value types: `Date`, `Time`, `DateTime`, `Duration`, `Interval`, `Timezone`. All immutable.
2. **errors** defines exception hierarchy: `ChrondelError` + subclasses for parse, timezone, arithmetic, comparison.
3. **parser** converts strings → DateTime/Date/Time/Duration. Supports ISO-8601, RFC-3339, forgiving parse_any().
4. **formatter** converts types → strings. strftime-compatible + ISO-8601 + custom format strings.
5. **timezone** handles timezone data (stdlib zoneinfo), DST transitions, wall-time-vs-instant semantics.
6. **arithmetic** implements add/subtract of Durations respecting DST; requires core_types + timezone.
7. **comparison** implements total ordering with instant-vs-wall distinction; requires core_types.
8. **intervals** implements 13 Allen relations on Intervals.
9. **cli** argparse-based CLI: parse, diff, convert subcommands.
10. **integration-examples** end-to-end tests plus example usage docs.

## Cross-chunk types

Types that multiple chunks consume. All chunks MUST import these from the listed module rather than re-define locally.

- `Date`, `Time`, `DateTime`, `Duration`, `Interval`, `Timezone` — defined in `src/chrondel/core_types.py`.
- `ChrondelError`, `ParseError`, `TimezoneError`, `ArithmeticError`, `ComparisonError` — defined in `src/chrondel/errors.py`.
- "Instant" is an internal concept, not a separate type: a DateTime becomes an instant via `.to_instant()` which returns an integer nanoseconds-since-epoch (UTC-referenced).

Do not re-define these types in any other module.

## scaffold

Package layout: `pyproject.toml`, `src/chrondel/{__init__.py, __main__.py}` (with cli stub), `tests/{__init__.py, test_smoke.py}`. Lint clean, import-clean passing. No logic.

## core_types

`src/chrondel/core_types.py`. Six immutable dataclass types:

- `Date(year, month, day)` — validates calendar (leap years, month lengths). Raises `ChrondelError` on invalid.
- `Time(hour, minute, second, nanosecond=0)` — 0-23, 0-59, 0-59, 0-999_999_999.
- `DateTime(date: Date, time: Time, tz: Timezone)` — combines; tz is required.
- `Duration(seconds: int, nanoseconds: int=0)` — signed; canonical form has `0 <= nanoseconds < 1_000_000_000`.
- `Interval(start: DateTime, end: DateTime)` — requires `start <= end` by total order (see comparison chunk).
- `Timezone(name: str)` — a thin wrapper around `zoneinfo.ZoneInfo(name)`, validated at construction.

All types have `__eq__`, `__hash__`, `__repr__`. No methods beyond construction validation.

## errors

`src/chrondel/errors.py`. Exception hierarchy:

- `ChrondelError(Exception)` — base
- `ParseError(ChrondelError)`
- `TimezoneError(ChrondelError)`
- `ArithmeticError(ChrondelError)` (distinct name from Python's — use `ChrondelArithmeticError` internally via `__all__`)
- `ComparisonError(ChrondelError)`

Each accepts `message: str, details: dict | None = None`. `__str__` returns message + details if present.

## parser

`src/chrondel/parser.py`. Public functions:

- `parse_iso8601(s: str) -> DateTime | Date | Time` — full ISO-8601 subset.
- `parse_rfc3339(s: str) -> DateTime` — strict RFC-3339.
- `parse_any(s: str) -> DateTime` — tries iso8601, rfc3339, common formats in order. Raises `ParseError` if all fail.
- `parse_duration(s: str) -> Duration` — ISO-8601 duration format `P1DT2H3M4S`.

Must handle: nanosecond precision (parse `2026-04-18T12:30:00.123456789Z`), offset forms (`+05:30`, `Z`, `+0530`), invalid → `ParseError` with clear message.

## formatter

`src/chrondel/formatter.py`. Public functions:

- `format_iso8601(dt: DateTime, *, nanoseconds: bool = False) -> str` — ISO-8601 output.
- `format_rfc3339(dt: DateTime) -> str` — RFC-3339 output.
- `format_strftime(dt: DateTime, fmt: str) -> str` — strftime directives. Note: `%Z` returns tzname, `%z` returns offset ±HHMM.
- `format_custom(dt: DateTime, fmt: str) -> str` — custom `{year:04d}-{month:02d}` Python-format-string style.

Must produce output that `parse_iso8601(format_iso8601(dt)) == dt` for valid DateTimes.

## timezone

`src/chrondel/timezone.py`. Public functions:

- `convert(dt: DateTime, target_tz: Timezone) -> DateTime` — preserves instant; changes wall time accordingly.
- `wall_time_equals(a: DateTime, b: DateTime) -> bool` — same year/month/day/hour/minute/second regardless of tz.
- `instant_equals(a: DateTime, b: DateTime) -> bool` — same UTC instant regardless of tz.
- `dst_transition_at(tz: Timezone, date: Date) -> tuple[Time, Time] | None` — returns (before, after) local times if DST transition on this date.

Handles DST "wall time" semantics for America/Los_Angeles, Europe/London, Australia/Sydney.

## arithmetic

`src/chrondel/arithmetic.py`. Public functions:

- `add(dt: DateTime, dur: Duration) -> DateTime` — wall-time addition: `add(2026-11-01T01:30 America/Los_Angeles, Duration(1 day)) == 2026-11-02T01:30 America/Los_Angeles` (DST-aware; wall time preserved).
- `subtract(dt: DateTime, dur: Duration) -> DateTime` — similarly DST-aware.
- `difference(a: DateTime, b: DateTime) -> Duration` — instant-based (converts both to UTC first).

Consumes core_types and timezone chunks.

## comparison

`src/chrondel/comparison.py`. Public functions:

- `compare(a: DateTime, b: DateTime) -> int` — returns -1/0/1 based on UTC instant.
- `total_order(items: list[DateTime]) -> list[DateTime]` — sorted by instant.
- `wall_time_compare(a: DateTime, b: DateTime) -> int` — compares wall-time components (ignores tz).

Consumes core_types chunk.

## intervals

`src/chrondel/intervals.py`. Public functions:

- `contains(interval: Interval, dt: DateTime) -> bool`
- `overlaps(a: Interval, b: Interval) -> bool`
- `allen_relation(a: Interval, b: Interval) -> str` — returns one of 13 strings: `before`, `after`, `meets`, `met_by`, `overlaps`, `overlapped_by`, `during`, `contains`, `starts`, `started_by`, `finishes`, `finished_by`, `equals`.
- `union(a: Interval, b: Interval) -> Interval | None` — only when intervals touch or overlap.
- `intersection(a: Interval, b: Interval) -> Interval | None`

## cli

`src/chrondel/cli.py`. argparse CLI with subcommands:

- `chrondel parse <str> [--format iso8601|rfc3339|strftime:%Y-%m-%d]`
- `chrondel diff <a> <b>` — prints Duration
- `chrondel convert <dt> --tz <tz>` — converts to target tz
- `--help` emits usage

`__main__.py` calls `main()`.

## integration-examples

`tests/integration/` directory with end-to-end examples: parse-format round-trip fuzz (500 iter), DST transition case, leap year case, interval overlap, CLI smoke. These verify acceptance gates against combined chunk output.
```

- [ ] **Step 4.2: Write `.skillgoid/chunks.yaml`**

Write this exact content:

```yaml
chunks:
  - id: scaffold
    description: "Package skeleton + smoke test."
    language: python
    gate_ids: [lint, import_clean]
    paths:
      - "pyproject.toml"
      - "src/chrondel/__init__.py"
      - "src/chrondel/__main__.py"
      - "tests/__init__.py"
      - "tests/test_smoke.py"

  - id: core_types
    description: "Six immutable dataclass types (Date/Time/DateTime/Duration/Interval/Timezone)."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [scaffold]
    paths:
      - "src/chrondel/core_types.py"
      - "tests/test_core_types.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_core_types.py"]}

  - id: errors
    description: "ChrondelError hierarchy."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [scaffold]
    paths:
      - "src/chrondel/errors.py"
      - "tests/test_errors.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_errors.py"]}

  - id: parser
    description: "ISO-8601 + RFC-3339 + parse_any; includes nanosecond precision."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [core_types, errors]
    paths:
      - "src/chrondel/parser.py"
      - "tests/test_parser.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_parser.py"]}

  - id: formatter
    description: "ISO-8601, RFC-3339, strftime, custom format output."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [core_types, errors]
    paths:
      - "src/chrondel/formatter.py"
      - "tests/test_formatter.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_formatter.py"]}

  - id: timezone
    description: "Timezone conversion + DST transition + wall/instant distinction."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [core_types, errors]
    paths:
      - "src/chrondel/timezone.py"
      - "tests/test_timezone.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_timezone.py"]}

  - id: arithmetic
    description: "DST-aware add/subtract/difference."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [core_types, timezone]
    paths:
      - "src/chrondel/arithmetic.py"
      - "tests/test_arithmetic.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_arithmetic.py"]}

  - id: comparison
    description: "UTC-instant ordering + wall-time comparison."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [core_types]
    paths:
      - "src/chrondel/comparison.py"
      - "tests/test_comparison.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_comparison.py"]}

  - id: intervals
    description: "13 Allen relations + union + intersection."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [core_types, comparison]
    paths:
      - "src/chrondel/intervals.py"
      - "tests/test_intervals.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_intervals.py"]}

  - id: cli
    description: "argparse CLI: parse, diff, convert subcommands."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [parser, formatter, arithmetic, timezone]
    paths:
      - "src/chrondel/cli.py"
      - "src/chrondel/__main__.py"
      - "tests/test_cli.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/test_cli.py"]}

  - id: integration-examples
    description: "End-to-end fuzz + Allen relations + DST + CLI smoke."
    language: python
    gate_ids: [lint, pytest_chunk]
    depends_on: [cli, intervals, arithmetic]
    paths:
      - "tests/integration/__init__.py"
      - "tests/integration/test_roundtrip.py"
      - "tests/integration/test_dst.py"
      - "tests/integration/test_allen.py"
    gate_overrides:
      pytest_chunk: {args: ["tests/integration/"]}
```

- [ ] **Step 4.3: Validate + run chunk_topo**

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
cd /home/flip/Development/skillgoid-test/chrondel
python -c "
import json, yaml, jsonschema
data = yaml.safe_load(open('.skillgoid/chunks.yaml'))
schema = json.load(open('/home/flip/Development/skillgoid/skillgoid-plugin/schemas/chunks.schema.json'))
jsonschema.validate(data, schema)
print('OK')
"
python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/chunk_topo.py \
  --chunks-file .skillgoid/chunks.yaml | python -m json.tool
```

Expected: `OK`, then wave output roughly matching:
- Wave 0: [scaffold]
- Wave 1: [core_types, errors] (parallel; depend only on scaffold)
- Wave 2: [formatter, parser, timezone] (parallel; depend on core_types+errors)
- Wave 3: [arithmetic, comparison] (parallel; parallel-safe via disjoint paths)
- Wave 4: [intervals]
- Wave 5: [cli]
- Wave 6: [integration-examples]

No overlap splits expected — all chunks have disjoint `paths:`. **If chunk_topo DOES split a wave, record as v0.9 finding** (would be a regression or unexpected v0.8 behavior).

- [ ] **Step 4.4: Update findings phase log**

Append:

```markdown
### plan
- blueprint.md: ~160 lines, 10+1 module headings (incl. Cross-chunk types).
- chunks.yaml: 11 chunks validated clean.
- chunk_topo output: <PASTE_WAVES>. No unexpected splits.
- Strict-acceptance approach preserved. H10 (schema validation during recovery) primed — iteration records must pass schema.
```

- [ ] **Step 4.5: Commit**

```bash
cd /home/flip/Development/skillgoid-test/chrondel
git add .skillgoid/blueprint.md .skillgoid/chunks.yaml
git commit -qm "plan: chrondel blueprint + 11-chunk decomposition"
```

---

## Task 5: Wave 0 — scaffold

- [ ] **Step 5.1: Pre-dispatch**

```bash
ls /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations/
```
Expected: empty.

- [ ] **Step 5.2: Dispatch scaffold subagent**

Use the reusable template (top of plan). `<CHUNK_ID>` = `scaffold`. Invoke slicer to get the sliced blueprint section:
```bash
python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/blueprint_slice.py \
  --blueprint /home/flip/Development/skillgoid-test/chrondel/.skillgoid/blueprint.md \
  --chunk-id scaffold
```
Paste slicer output as `<PASTE_SLICED_BLUEPRINT>`.

Single Agent() call, `general-purpose`, `sonnet`.

- [ ] **Step 5.3: Verify + append to findings**

```bash
git log --oneline -2
git show --name-only HEAD --format=
```

Verify scaffold-001.json + scaffolded files committed scoped.

Append phase log:
```markdown
### Wave 0 — scaffold
- iteration: scaffold-001.json, gates green (lint + import_clean).
- Commit scope: clean (chunk's paths only + iter json).
```

---

## Task 6: Wave 1 — core_types + errors (2 parallel)

- [ ] **Step 6.1: Dispatch BOTH in a single message**

Two Agent() calls in one assistant message. Slice blueprint for each (core_types + errors).

- [ ] **Step 6.2: Wait for both, verify**

```bash
git log --oneline -4
ls /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations/
```

Expected: both commits disjoint (values.py-style overlap concerns don't apply — core_types.py and errors.py are separate files).

- [ ] **Step 6.3: Update findings**

Append phase log entry. If both pass first try (likely for simple type/error chunks), note as baseline for H1 (organic iteration expected later, not here).

---

## Task 7: Wave 2 — parser + formatter + timezone (3 parallel — watch for S1 organic iteration)

- [ ] **Step 7.1: Dispatch ALL THREE in a single message**

Three Agent() calls. Slice blueprint for each chunk. Each gets core_types.py + errors.py as pre-existing imports.

- [ ] **Step 7.2: Wait for all three, verify**

```bash
git log --oneline -5
ls /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations/
```

**S1 DETECTION:** If any subagent reports `exit_reason != "success"` (gates failed on iter 1), that's organic iteration evidence. Record which chunk failed and the failure mode.

**If all three pass iter 1:** the strict-acceptance approach didn't fire as expected. Note in findings — may need to tighten criteria for later chunks.

- [ ] **Step 7.3: If S1 fires (organic failure), redispatch the failing chunk's subagent**

Use the template again with `<CHUNK_ID>=<the-failing-one>` and include the prior iteration's gate_report as `<PASTE_PRIOR_ITER_RECORDS>`. Subagent should see the failure and fix it.

- [ ] **Step 7.4: Update findings**

Append phase log entry. Update S1 status in the scenario tracker.

---

## Task 8: INTERVENTION — S2 forced stall on `formatter`

Precondition: `formatter` has completed at least one iteration (from Task 7). If formatter passed first try, pick `parser` or `timezone` instead.

- [ ] **Step 8.1: Identify the latest passing or failing iteration for `formatter`**

```bash
ls /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations/ | grep formatter
cat /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations/formatter-001.json | python -c "
import json, sys
d = json.load(sys.stdin)
print('exit_reason:', d.get('exit_reason'))
print('gate_report.passed:', d['gate_report']['passed'])
print('failure_signature:', d.get('failure_signature'))
"
```

- [ ] **Step 8.2: Revert the subagent's implementation to reintroduce the SAME bug**

```bash
cd /home/flip/Development/skillgoid-test/chrondel
# If formatter passed: first find the commit and revert JUST the non-test file.
# If formatter already failed: leave it as-is; dispatch iter 2 which should produce same failure.
```

Goal: make iter 2's gate_report produce the same stderr prefix as iter 1 → same failure_signature.

Concrete method: in `src/chrondel/formatter.py`, introduce the known LLM-typo: use `%Z` where `%z` is required (or vice versa). This will fail the same way across iterations.

- [ ] **Step 8.3: Dispatch formatter iter 2**

Template with `<CHUNK_ID>=formatter`, NNN=002, prior iter as context.

**Critical:** after iter 2 returns, verify `scripts/stall_check.py` computes the same failure_signature as iter 1 (the point of S2). If the signatures differ despite identical failures, that's a v0.9 finding — `stall_check.py` is fragile.

- [ ] **Step 8.4: Verify loop skill's stall detection fires**

The loop skill's step 9 says: if current iteration's `failure_signature` equals previous, write `exit_reason: "stalled"` and return. Since we're driving manually, we write this into formatter-002.json ourselves:

```bash
# Check the computed signature
python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/stall_check.py \
  /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations/formatter-002.json
```

Compare to formatter-001.json's signature. If equal: write `exit_reason: "stalled"` in formatter-002.json.

- [ ] **Step 8.5: Update findings**

Append with H2 status. If stall_check was deterministic + loop-skill-prose correctly identified the stall: H2 confirmed. If signatures differed for identical failures, or the loop skill didn't clearly specify the check, note as finding.

---

## Task 9: INTERVENTION — S6 gate-guard Stop-block

Precondition: formatter is in `stalled` state from Task 8 (or any chunk is failing with budget remaining).

- [ ] **Step 9.1: Simulate a Stop event via gate-guard.sh**

```bash
cd /home/flip/Development/skillgoid-test/chrondel
CLAUDE_PROJECT_DIR=/home/flip/Development/skillgoid-test/chrondel \
  /home/flip/Development/skillgoid/skillgoid-plugin/hooks/gate-guard.sh
echo "exit: $?"
```

Expected: hook emits a JSON `{"decision": "block", "reason": "..."}` payload mentioning failing gates and loop budget remaining.

- [ ] **Step 9.2: Update findings**

Confirm H7. If the hook doesn't block, or the reason is unhelpful, record as finding. If the hook fires correctly but only surfaces via the `reason` field in a way LLMs might miss, note UX concern.

---

## Task 10: INTERVENTION — S3 unstick injection

Precondition: formatter is stalled.

- [ ] **Step 10.1: Manually execute the unstick skill's procedure**

Per `skills/unstick/SKILL.md`, the procedure is to re-dispatch the chunk's subagent with a one-sentence hint injected. Since we're driving manually, construct a dispatch prompt that includes:

```
## Unstick hint (v0.4 feature)
"The strftime %Z directive returns the tzname, not the offset; use %z for the numeric offset ±HHMM."

## Prior stall context
<PASTE_formatter-002.json>

The above hint should directly resolve the bug in the prior iteration.
```

Dispatch formatter iter 3 subagent.

- [ ] **Step 10.2: Verify the hint actually unblocks**

```bash
ls /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations/ | grep formatter
cat /home/flip/Development/skillgoid-test/chrondel/.skillgoid/iterations/formatter-003.json | \
  python -c "import json,sys; print(json.load(sys.stdin)['gate_report']['passed'])"
```

Expected: iter 3 passes. If it does, H3 confirmed.

If iter 3 ALSO fails with the same signature, H3 falsified — the hint mechanism doesn't actually unblock. Record as 🔴.

- [ ] **Step 10.3: Update findings**

S3 + H3 status.

---

## Task 11: Checkpoint — prepare for S5 (SessionStart resume)

**Files:** none modified

- [ ] **Step 11.1: Ensure clean checkpoint state**

Wave 2 (parser + formatter + timezone) is complete. Wave 3 hasn't started. iterations/ contains: scaffold-001, core_types-001, errors-001, parser-001, formatter-{001,002,003}, timezone-001.

- [ ] **Step 11.2: Commit project state (if any untracked files)**

```bash
cd /home/flip/Development/skillgoid-test/chrondel
git status -s
# If anything is untracked or modified, commit it
git log --oneline | head -5
```

- [ ] **Step 11.3: Instruct the user to SIGKILL this session and start a fresh one**

This is the first genuine multi-session requirement. The plan MUST pause here for the user to:
1. Close the current Claude Code session.
2. Open a new Claude Code session in `/home/flip/Development/skillgoid-test/chrondel/`.
3. Observe whether SessionStart hook (`detect-resume.sh`) emits an `additionalContext` payload.
4. Run `/skillgoid:build resume` to continue.

**Output to user before pausing:**

> Checkpoint reached. Close this session and open a new Claude Code session in `~/Development/skillgoid-test/chrondel/` to continue the experiment. The next step (S5) requires a fresh session to legitimately test SessionStart + resume.

---

## Task 12: INTERVENTION — S5 SessionStart resume (new session)

**New session required.** This task executes in the FRESH Claude Code session from Task 11's pause.

- [ ] **Step 12.1: Observe SessionStart hook output**

When the fresh session starts in `~/Development/skillgoid-test/chrondel/`, the SessionStart hook should fire automatically and emit a context payload.

Check for it in the session's initial output. Expected structure (from `hooks/detect-resume.sh`):
- Mentions "Resuming Skillgoid project"
- Counts chunks from chunks.yaml (11 chunks expected)
- References the latest iteration's chunk_id and exit_reason
- Suggests `/skillgoid:build resume` or `/skillgoid:build status`

Record the exact payload in findings.

- [ ] **Step 12.2: Run `/skillgoid:build status`**

Per v0.2+ the build skill should accept `status` as a subcommand and print a summary. In the fresh session, manually execute the build skill's status procedure: enumerate chunks from chunks.yaml, cross-reference with latest iterations/*.json per chunk, print exit_reason per chunk.

Verify the status output reflects actual state: wave 2 done, wave 3 pending, formatter needed iters 1/2/3.

- [ ] **Step 12.3: Run `/skillgoid:build resume`**

Manually execute the build skill's resume procedure: find the first chunk that has NOT yet exited `success`, continue the per-chunk dispatch loop starting there.

In our case: wave 2 is complete (last formatter iter is 3 and passed). Next chunks to dispatch are wave 3: arithmetic + comparison.

- [ ] **Step 12.4: Update findings**

S5 + H5 + H6 status. If the hook payload was empty, unhelpful, or missing: 🟡. If build-skill-prose for resume didn't clearly specify where to pick up: 🟡.

---

## Task 13: Wave 3 — arithmetic + comparison (2 parallel)

- [ ] **Step 13.1: Dispatch BOTH in a single message**

Standard pattern.

- [ ] **Step 13.2: Verify + update findings**

If either chunk needs iteration, note as additional H1 evidence.

---

## Task 14: Wave 4 — `intervals` with S4 budget exhaustion

- [ ] **Step 14.1: Tighten max_attempts for intervals**

Create a one-off criteria override for the intervals chunk. Two options:
(a) Modify `.skillgoid/criteria.yaml` to set `loop.max_attempts: 2` — BUT this affects all chunks. Not ideal.
(b) Dispatch the intervals subagent with an explicit "you have max_attempts=2 in your loop budget" override in the prompt.

Use (b). Subagent prompt includes: "Your loop budget is capped at max_attempts=2 for S4 evidence. Do not loop beyond iter 2."

Intervals has 13 Allen relations. First-iter LLM output often misses 2-3 of them (meets vs met_by, during vs contains symmetries are easy to swap). Iter 2 likely fixes some but may still miss edges.

- [ ] **Step 14.2: Dispatch intervals iter 1**

Standard dispatch. If gate_report_passed = true, S4 can't fire; note and skip to Task 15.

- [ ] **Step 14.3: If iter 1 fails, dispatch iter 2 with prior context**

Include iter 1's gate_report as prior context.

- [ ] **Step 14.4: If iter 2 also fails: write budget_exhausted iteration record**

Manually write intervals-002.json with `exit_reason: "budget_exhausted"` IF iter 2 fails. This simulates the loop's step 9 "Budget exhausted" exit condition.

Verify schema still accepts the record (v0.8 validation).

- [ ] **Step 14.5: Update findings**

S4 + H4 status. Also checks H10 (v0.8 schema validates budget_exhausted records cleanly).

---

## Task 15: INTERVENTION — S8 retrospect-only (if S4 fired)

Precondition: intervals exited `budget_exhausted` in Task 14.

If intervals passed without budget exhaustion, SKIP this task and proceed to Task 16.

- [ ] **Step 15.1: Invoke retrospect-only manually**

Per `skills/retrospect/SKILL.md` + `skills/build/SKILL.md` subcommand dispatch:
1. Read all iteration JSONs.
2. Read goal.md, blueprint.md, chunks.yaml.
3. Write `.skillgoid/retrospective.md` with outcome: `partial` (since intervals failed).
4. Optionally curate vault.
5. Run `metrics_append.py`.

Follow the retrospect skill prose. Verify each step produces expected output.

- [ ] **Step 15.2: Update findings**

S8 + H9 status. Note any friction in the retrospect skill when applied to a partial-completion project.

---

## Task 16: Wave 5 — `cli` (1 chunk)

Dispatch cli subagent. Standard pattern.

If S8 fired (retrospect-only triggered), this task MAY be skipped — but running it anyway tests whether the pipeline can continue after a retrospect-only. Recommendation: continue, to exercise more chunks.

- [ ] **Step 16.1: Dispatch cli subagent**

- [ ] **Step 16.2: Verify + update findings**

---

## Task 17: Wave 6 — `integration-examples` with S7 integration retry

- [ ] **Step 17.1: Dispatch integration-examples subagent**

Standard dispatch.

- [ ] **Step 17.2: Run integration_gates manually**

Per `skills/build/SKILL.md` step 4, after all per-chunk gates pass, run integration_gates:

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
cd /home/flip/Development/skillgoid-test/chrondel
# Build a temp criteria with just integration_gates
python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/measure_python.py \
  --project /home/flip/Development/skillgoid-test/chrondel \
  --criteria-stdin <<'EOF' | python -m json.tool
gates:
  - id: cli_help
    type: cli-command-runs
    command: ["python", "-m", "chrondel", "--help"]
    expect_exit: 0
    expect_stdout_match: "usage:"
    env:
      PYTHONPATH: "src"
  - id: cli_roundtrip
    type: run-command
    command:
      - "bash"
      - "-c"
      - |
        set -euo pipefail
        OUT=$($SKILLGOID_PYTHON -m chrondel parse "2026-04-18T12:30:00Z" --format iso8601)
        [ "$OUT" = "2026-04-18T12:30:00Z" ]
    expect_exit: 0
    env:
      PYTHONPATH: "src"
EOF
```

- [ ] **Step 17.3: If integration fails, verify retry logic**

Per the build skill step 4g: identify suspect chunk from the failing gate's stderr, re-dispatch that chunk's subagent with `integration_failure_context` injected. The cli chunk is the most likely suspect.

Verify the build-skill prose actually specifies how to identify the suspect chunk + inject the failure context. Any ambiguity is a v0.9 finding.

- [ ] **Step 17.4: Update findings**

S7 + H8 status.

---

## Task 18: Retrospect + findings synthesis

- [ ] **Step 18.1: Run metrics_append**

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/metrics_append.py \
  --skillgoid-dir /home/flip/Development/skillgoid-test/chrondel/.skillgoid \
  --slug chrondel-recovery-stress
tail -1 ~/.claude/skillgoid/metrics.jsonl
```

- [ ] **Step 18.2: Write `chrondel/.skillgoid/retrospective.md`**

Same shape as minischeme retrospective. Include:
- Outcome (success / partial / aborted — expected: `partial` since S4 likely fires)
- Hypotheses table updated with confirmed/falsified for each H1–H10
- Scenarios table updated with fired/skipped for each S1–S8
- Headline findings
- v0.9 prioritization recommendation (ROI-ordered)

- [ ] **Step 18.3: Synthesize v0.9-findings.md**

Append a `## Synthesis` section at the end with:
- All findings' severities + hypothesis links
- Scenarios fired / not fired
- Recommended v0.9 ROI-ordered priorities
- Method note on same-driver-bias + multi-session requirement

- [ ] **Step 18.4: Commit retrospective**

```bash
cd /home/flip/Development/skillgoid-test/chrondel
git add .skillgoid/retrospective.md
git commit -qm "retrospect: chrondel recovery stress run — v0.9 findings synthesized"
```

---

## Self-review checklist

- [x] **Spec coverage:** every spec section maps to tasks.
  - Project setup (T1); retrieve (T2.1); clarify (T2); feasibility (T3); plan (T4)
  - Waves 0-6 (T5, T6, T7, T13, T14, T16, T17)
  - 8 scenarios (S1: T7; S2: T8; S3: T10; S4: T14; S5: T12; S6: T9; S7: T17.3; S8: T15)
  - Retrospect (T18)
  - H1-H10 all tested via scenarios (table in findings log tracks confirmed/falsified)
- [x] **No placeholders:** no TBDs, no "similar to task N," no "handle appropriate edge cases." Every code step has actual commands + expected outputs.
- [x] **Multi-session requirement explicit.** T11 is the mandatory pause; T12 is the fresh-session continuation.
- [x] **Intervention tasks (T8, T9, T10, T12, T14, T15) clearly distinguished from standard wave-dispatch tasks.** Each intervention specifies the exact action (revert file, execute hook manually, invoke unstick procedure, kill session).
- [x] **Stopping criteria** from spec preserved: 8 scenarios exercised OR 🔴 blocker OR 5+ 🟡 OR 4+ chunks budget-exhausted. Task 18's retrospect is the terminal state.
- [x] **Reuses the subagent prompt template** (defined once at top) for all chunk dispatches. No duplication.
- [x] **H5/H6 (SessionStart + resume) only genuine-test path requires multi-session** — spec flagged this risk. T11→T12 handles it.
