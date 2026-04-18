# Skillgoid v0.8 Stress-Test Execution Plan — `minischeme`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note:** Tasks in this plan dispatch chunk-execution subagents that are *part of the experiment*. The plan-executor (you) is the experimental driver, not a chunk implementer. "Implement the failing test" patterns from typical SDD plans don't apply here — tasks observe, dispatch, and record.

**Goal:** Run Skillgoid v0.7 against an 18-chunk single-language project (`minischeme`, a Lisp-flavored interpreter) to surface v0.8 priorities. Stop at the first stopping criterion (most likely after wave 6 — the 4-way parallel headline).

**Architecture:** Plan-executor manually interprets `skills/*/SKILL.md` files to drive the build → measure → reflect pipeline. Per-chunk work is dispatched to `general-purpose` subagents via the `Agent` tool, with parallel waves emitting all `Agent()` calls in a single message so they execute concurrently. Findings collected in an append-only log as observed.

**Tech Stack:** Python 3.11+, sqlite3 stdlib (none in this experiment, the project itself is pure-stdlib). Plugin venv at `/home/flip/Development/skillgoid/skillgoid-plugin/.venv/` for measure_python.py + helper scripts.

**Spec:** `docs/superpowers/specs/2026-04-18-skillgoid-v0.8-stress-test-design.md` (commit `6f7e45c`).

**Evidence target:** Append findings to `~/Development/skillgoid-test/v0.8-findings.md`. Falsify or confirm hypotheses H1–H10 listed in the spec.

---

## Working layout

```
~/Development/skillgoid-test/
├── v0.8-findings.md                     ← append-only findings log (created Task 1)
├── minischeme/                          ← project tree (created Task 1)
│   ├── .skillgoid/
│   │   ├── goal.md                      ← Task 2
│   │   ├── criteria.yaml                ← Task 2
│   │   ├── blueprint.md                 ← Task 4
│   │   ├── chunks.yaml                  ← Task 4
│   │   ├── iterations/
│   │   │   ├── scaffold-001.json        ← Task 5 (subagent)
│   │   │   ├── errors-001.json          ← Task 6
│   │   │   ├── values-001.json          ← Task 6
│   │   │   └── ...
│   │   └── retrospective.md             ← Task 17
│   ├── src/minischeme/                  ← created chunk-by-chunk by subagents
│   ├── tests/                           ← created chunk-by-chunk
│   └── pyproject.toml                   ← Task 5 (scaffold subagent)
└── (other test projects unchanged)
```

---

## Reusable subagent prompt template

Every chunk-execution dispatch uses this template. The plan-executor fills in the placeholders at dispatch time. Defined here once so subsequent tasks can reference it instead of inlining.

```
You are a Skillgoid chunk subagent executing ONE ITERATION of chunk `<CHUNK_ID>` for the minischeme stress-test project. This is a v0.8-evidence experiment — DO NOT loop or retry on gate failure. Do the iteration once, write the iteration JSON, commit, return.

## Context
- Project dir: /home/flip/Development/skillgoid-test/minischeme
- Plugin dir: /home/flip/Development/skillgoid/skillgoid-plugin
- Plugin venv python: /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python
- v0.7 conventions apply: iteration files named `<chunk_id>-NNN.json`; git_iter_commit takes --chunks-file; per-chunk paths: declared.

## Your chunk (verbatim from chunks.yaml)
<PASTE_CHUNK_YAML_BLOCK>

## Critical files to read before starting
- /home/flip/Development/skillgoid-test/minischeme/.skillgoid/blueprint.md (your section: <BLUEPRINT_SECTION_NAME>)
- /home/flip/Development/skillgoid-test/minischeme/.skillgoid/criteria.yaml (gates referenced by your gate_ids)

## Past lessons summary
<PASTE_RETRIEVE_SUMMARY>

## Build step
Implement the chunk per blueprint. Match the public interface signatures exactly so other chunks' assumptions hold. Write tests under tests/ that exercise your code in-process (per pytest-cov subprocess-coverage caveat — see python-lessons.md).

## Measure step
Build a temp criteria file at /tmp/<chunk_id>_criteria.yaml containing only the gates your chunk cares about (subset of criteria.yaml gates[] whose id is in your gate_ids). Invoke:
  /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
    /home/flip/Development/skillgoid/skillgoid-plugin/scripts/measure_python.py \
    --project /home/flip/Development/skillgoid-test/minischeme \
    --criteria-stdin < /tmp/<chunk_id>_criteria.yaml
Parse JSON from stdout. Keep the full gate_report.

## Reflect step — write iteration JSON
Filename: /home/flip/Development/skillgoid-test/minischeme/.skillgoid/iterations/<chunk_id>-001.json (v0.7 convention).
Required fields per /home/flip/Development/skillgoid/skillgoid-plugin/schemas/iterations.schema.json: iteration, chunk_id, gate_report.
Populate also: started_at, ended_at, gates_run, reflection, notable, failure_signature, exit_reason.

Compute failure_signature: write the gate_report (alone) to a tmp file under tempfile.gettempdir(), then run:
  /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
    /home/flip/Development/skillgoid/skillgoid-plugin/scripts/stall_check.py \
    <gate_report_tmp_file>
Output is a 16-char hex; place it in failure_signature.

Set exit_reason: "success" if gate_report.passed else "in_progress".
Set notable: true if you hit something unexpected (slow lexer, fragile error type, surprising stdlib edge case). Boring iterations stay false.

## Git commit step
Run from project dir:
  /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
    /home/flip/Development/skillgoid/skillgoid-plugin/scripts/git_iter_commit.py \
    --project /home/flip/Development/skillgoid-test/minischeme \
    --iteration .skillgoid/iterations/<chunk_id>-001.json \
    --chunks-file .skillgoid/chunks.yaml

This MUST succeed (exit 0). If it doesn't, report it in your return — that's a v0.7 regression.

## Scratch file hygiene (v0.7 convention)
Write all temp files (stall_check input, criteria subset) under tempfile.gettempdir(), NEVER inside the minischeme project dir.

## Return format
Return JSON on your final message:
{
  "chunk_id": "<id>",
  "iteration_file": ".skillgoid/iterations/<id>-001.json",
  "gate_report_passed": bool,
  "failing_gates": ["..."],
  "exit_reason": "success" | "in_progress",
  "commit_sha": "<short sha>",
  "files_in_commit": ["..."],          # from `git show --name-only HEAD`
  "v0_8_friction_observations": ["..."],
  "race_evidence": {                    # only relevant for parallel waves
    "siblings_present_at_dir_scan": ["..."],
    "notes": "..."
  }
}
```

---

## Task 1: Project + findings setup

**Files:**
- Create: `/home/flip/Development/skillgoid-test/minischeme/` (empty dir)
- Create: `/home/flip/Development/skillgoid-test/minischeme/.gitignore`
- Create: `/home/flip/Development/skillgoid-test/v0.8-findings.md`

- [ ] **Step 1.1: Verify v0.7 baseline + plugin venv**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
. .venv/bin/activate
pytest -q && ruff check .
git log --oneline -1
```
Expected: 134 tests pass, ruff clean, latest commit on main is the v0.7 merge or later.

- [ ] **Step 1.2: Create project tree**

```bash
mkdir -p /home/flip/Development/skillgoid-test/minischeme/.skillgoid/iterations
mkdir -p /home/flip/Development/skillgoid-test/minischeme/.skillgoid/integration
cd /home/flip/Development/skillgoid-test/minischeme
git init -q
```

- [ ] **Step 1.3: Write `.gitignore`**

```bash
cat > /home/flip/Development/skillgoid-test/minischeme/.gitignore <<'EOF'
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

Create `/home/flip/Development/skillgoid-test/v0.8-findings.md` with this exact content:

```markdown
# Skillgoid v0.8 findings — minischeme stress run

Running date: 2026-04-18
Target: `~/Development/skillgoid-test/minischeme/` — Lisp-flavored interpreter, 18 chunks across 11 waves
Skillgoid version under test: v0.7 (commit 5c966f3 + merge)
Driver: Claude (Opus 4.7) manually interpreting `skills/*/SKILL.md` (same pattern as taskbridge)
Spec: `~/Development/skillgoid/skillgoid-plugin/docs/superpowers/specs/2026-04-18-skillgoid-v0.8-stress-test-design.md`

## Hypotheses tracker

| # | Hypothesis | Status |
|---|---|---|
| H1 | _commit_lock holds at width-4 | pending |
| H2 | chunk_topo correct on 18-chunk DAG | pending |
| H3 | Blueprint context budget OK at scale | pending |
| H4 | vault_filter still surfaces relevant lessons | pending |
| H5 | max_attempts=5 enough across 18 chunks | pending |
| H6 | Cross-chunk type-contract failures surface within responsible chunk | pending |
| H7 | Plan-refinement-mid-build remains unneeded (8th run) | pending |
| H8 | notable: true rate stays sane | pending |
| H9 | <chunk_id>-NNN.json convention holds at 18 chunks | pending |
| H10 | flock helper degrades gracefully on width-1 waves | pending |

## Findings

(Severity: 🔴 blocking, 🟡 friction, 🟢 minor)

## Phase log

(Filled in as the experiment runs.)
```

- [ ] **Step 1.5: Commit baseline state**

```bash
cd /home/flip/Development/skillgoid-test/minischeme
git add .gitignore
git commit -qm "init: minischeme stress-test scaffold"
git log --oneline
```

---

## Task 2: Retrieve + Clarify (write goal.md + criteria.yaml inline)

**Files:**
- Create: `/home/flip/Development/skillgoid-test/minischeme/.skillgoid/goal.md`
- Create: `/home/flip/Development/skillgoid-test/minischeme/.skillgoid/criteria.yaml`

- [ ] **Step 2.1: Run vault_filter to get current active lessons**

```bash
/home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
  /home/flip/Development/skillgoid/skillgoid-plugin/scripts/vault_filter.py \
  --lessons-file ~/.claude/skillgoid/vault/python-lessons.md \
  --plugin-json /home/flip/Development/skillgoid/skillgoid-plugin/.claude-plugin/plugin.json
```
Expected: JSON with active + resolved lesson titles. **Record the active titles in v0.8-findings.md phase log under "retrieve" — they shape the subagent prompts going forward.**

- [ ] **Step 2.2: Write `goal.md`**

```markdown
# Goal

Build `minischeme`, a Lisp-flavored scripting language interpreter in Python 3.11+. Programs in minischeme run via `minischeme <file.scm>` or interactively via `minischeme` (REPL mode).

## Scope

- First-class functions with lexical-scope closures
- Numbers (int + float), booleans, strings, lists, hashmaps, nil
- Special forms: `if`, `cond`, `let`, `lambda`, `define`, `begin`, `set!`, `quote`, `try`, `throw`
- ~15 builtins: `+ - * / % = < > <= >= and or not list cons car cdr append length map filter reduce concat substring string-length string->list print println read-line apply`
- Tail-call optimization via trampoline
- Error handling with throw/try
- File-load form `(load "path/to/file.scm")` for single-file modules
- REPL with line-by-line evaluation
- CLI: `minischeme <file>` (script mode) and `minischeme` (REPL mode)

## Non-goals

- Macros, continuations, GC tuning, FFI, multi-file imports beyond `load`
- Distribution to PyPI
- Performance benchmarks (correctness first; optimization later if needed)

## Success signals

- A corpus of ~10 example programs in `tests/examples/` runs to expected output via `minischeme tests/examples/<name>.scm`
- All chunk-level test suites green
- Tail-recursive functions don't blow the stack (e.g., `(define (loop n) (if (= n 0) 'done (loop (- n 1))))` returns `done` for n=10000)
- Closures correctly capture lexical scope
- `(try (throw 'err) (lambda (e) e))` returns `err`

## Constraints

- Python 3.11+
- Pure stdlib (no third-party runtime deps)
- Single source tree (`src/minischeme/`)
```

Write this to `/home/flip/Development/skillgoid-test/minischeme/.skillgoid/goal.md`.

- [ ] **Step 2.3: Write `criteria.yaml`**

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
    module: minischeme
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
    command: ["python", "-m", "minischeme", "--help"]
    expect_exit: 0
    expect_stdout_match: "usage:"
    env:
      PYTHONPATH: "src"

  - id: cli_eval_smoke
    type: run-command
    command:
      - "bash"
      - "-c"
      - |
        set -euo pipefail
        echo '(println (+ 1 2))' > /tmp/minischeme_smoke.scm
        OUT=$($SKILLGOID_PYTHON -m minischeme /tmp/minischeme_smoke.scm)
        echo "$OUT" | grep -q "^3$"
    expect_exit: 0
    env:
      PYTHONPATH: "src"

  - id: cov
    type: coverage
    target: "minischeme"
    min_percent: 80
    compare_to_baseline: false

integration_retries: 2

acceptance:
  - "minischeme tests/examples/factorial.scm prints 120"
  - "minischeme tests/examples/closures.scm passes its embedded assertions"
  - "minischeme tests/examples/tail_recursive_loop.scm completes for n=10000 without stack overflow"
  - "minischeme tests/examples/throw_catch.scm returns the thrown value"
  - "Both CLI modes (script and REPL) launch successfully and respect --help"

models:
  chunk_subagent: sonnet
  integration_subagent: haiku
```

Note the v0.7 conventions: coverage in `integration_gates` (not per-chunk gate_ids); `env:` declared on every gate that needs it.

- [ ] **Step 2.4: Validate criteria.yaml**

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
cd /home/flip/Development/skillgoid-test/minischeme
python -c "
import json, yaml, jsonschema
data = yaml.safe_load(open('.skillgoid/criteria.yaml'))
schema = json.load(open('/home/flip/Development/skillgoid/skillgoid-plugin/schemas/criteria.schema.json'))
jsonschema.validate(data, schema)
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 2.5: Update v0.8-findings.md phase log**

Append to `/home/flip/Development/skillgoid-test/v0.8-findings.md` under `## Phase log`:

```markdown
### retrieve
- Active vault lessons: <titles from Step 2.1>
- Note any v0.7 lessons that should be present but aren't (relevant for H4).

### clarify
- goal.md and criteria.yaml written manually (auto-mode pattern).
- v0.7 conventions applied: coverage in integration_gates, env: on env-sensitive gates.
```

- [ ] **Step 2.6: Commit**

```bash
cd /home/flip/Development/skillgoid-test/minischeme
git add .skillgoid/goal.md .skillgoid/criteria.yaml
git commit -qm "clarify: minischeme goal + criteria"
```

---

## Task 3: Feasibility check (manual interpretation + record findings)

**Files:** none modified

- [ ] **Step 3.1: Per-gate feasibility checks**

Run each check manually and record results inline:

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
which ruff pytest
python -m pytest --cov --version 2>&1 | head -3
which bash
```
Expected: ruff, pytest both resolvable from venv; pytest-cov available; bash on PATH.

- [ ] **Step 3.2: Check gate `env:` paths**

`env: {PYTHONPATH: "src"}` is relative; resolves to `<project>/src/`. Doesn't exist yet (scaffold creates it). Per v0.5 feasibility-scaffolding-awareness, this is a soft warning, not a hard fail. Note in findings.

- [ ] **Step 3.3: Update v0.8-findings.md phase log**

Append:

```markdown
### feasibility
- All Python tools resolvable from plugin venv (pytest, ruff, pytest-cov).
- bash resolvable for shell-string integration gates.
- env: PYTHONPATH=src is a relative path that doesn't exist yet — soft warning per v0.5; scaffold chunk creates it.
- Decision: proceed.
```

No commit — feasibility is observation only.

---

## Task 4: Plan (write blueprint.md + chunks.yaml inline, run chunk_topo)

**Files:**
- Create: `/home/flip/Development/skillgoid-test/minischeme/.skillgoid/blueprint.md`
- Create: `/home/flip/Development/skillgoid-test/minischeme/.skillgoid/chunks.yaml`

- [ ] **Step 4.1: Write `blueprint.md`**

Write to `/home/flip/Development/skillgoid-test/minischeme/.skillgoid/blueprint.md`. The blueprint must include `## <chunk-id>` headings for every chunk so each subagent prompt can include "your section is `## <chunk-id>`". Full content:

```markdown
# Blueprint — minischeme

## Architecture overview

A bytecode-free tree-walking interpreter. The pipeline is:

1. **Lexer** turns source text into tokens (`Lexer.tokenize(src) -> list[Token]`).
2. **Parser** turns tokens into an AST of `SExpr` nodes (atoms + lists).
3. **Evaluator** walks the AST in an `Environment`, dispatching on node type. Special forms are handled in-evaluator; builtins and user-defined functions go through a uniform call protocol.
4. **Tail-call optimization** is a trampoline-based wrapper around the evaluator's call dispatch — `eval` returns either a value or a "thunk" that's resumed in a loop.
5. **REPL** is `parser + evaluator` in a read loop. **CLI** is `parser + evaluator` against a file.

Cross-chunk contracts (these MUST stay stable across chunks; changes mid-build break downstream chunks):

- `Token` shape: `{type: TokenType, value: str | int | float | bool, line: int, col: int}`
- `SExpr` shape: tagged-union of `Atom(value)`, `Symbol(name)`, `Pair(head, tail)`, `Nil`. Emitted by parser; consumed by evaluator.
- `Environment` interface: `get(name) -> Value | raises NameError`, `set(name, value)`, `extend(bindings: dict) -> Environment` (returns child frame), `define(name, value)` for top-level.
- `Value` union: `int | float | str | bool | list[Value] | dict[Value, Value] | Closure | Builtin | None` (None = nil). All builtins and special forms operate on this union.
- `Closure` shape: `{params: list[str], body: SExpr, env: Environment}`.
- `Trampoline` protocol: an evaluator that supports TCO returns either `Value` or `TailCall(closure, args)`. The driver loop unwraps until it hits a `Value`.
- `MinischemeError` base + subclasses (`LexError`, `ParseError`, `NameError`, `TypeError`, `ArityError`, `UserError`). All raised exceptions in the runtime path inherit from `MinischemeError`.

## scaffold

Project skeleton: `pyproject.toml` (with `[project.scripts] minischeme = "minischeme.cli:main"`), `src/minischeme/__init__.py`, `src/minischeme/__main__.py`, `tests/__init__.py`, `tests/test_smoke.py` (single import test). Lint clean.

## errors

`src/minischeme/errors.py`. Defines `MinischemeError` base + the 6 subclasses listed above. Each accepts `message: str, line: int | None = None, col: int | None = None` and renders nicely in `__str__`. No logic — just types.

## values

`src/minischeme/values.py`. Defines the value sentinel `Nil` (singleton), the `Closure` dataclass (`params`, `body`, `env`), the `Builtin` dataclass (`name`, `fn`, `arity` where `arity = (min, max | None)`), and a `TailCall` dataclass (`closure`, `args`). Plus type-check helpers: `is_truthy(v) -> bool` (everything except `False` and `Nil` is truthy), `value_repr(v) -> str` (Lisp-style printing).

## lexer

`src/minischeme/lexer.py`. `Token` dataclass (type, value, line, col). `TokenType` enum (`LPAREN`, `RPAREN`, `QUOTE`, `SYMBOL`, `INTEGER`, `FLOAT`, `STRING`, `BOOL`, `EOF`). Public function: `tokenize(src: str) -> list[Token]`. Strips whitespace + `;` line comments. Raises `LexError` on bad escapes / unterminated strings.

## environment

`src/minischeme/environment.py`. `Environment` class with `parent: Environment | None`, `bindings: dict[str, Value]`. Methods: `get(name)` (walks parent chain, raises `NameError` if not found), `set(name, value)` (sets in nearest scope that already has it; raises if not found), `define(name, value)` (always sets in current scope), `extend(bindings: dict) -> Environment` (returns child frame). Constructor `Environment(parent=None, bindings=None)`.

## parser

`src/minischeme/parser.py`. Recursive-descent over the token stream. Public function: `parse(tokens: list[Token]) -> list[SExpr]` (returns top-level forms). The `SExpr` ADT lives here too: `Atom(value)`, `Symbol(name)`, `Pair(head, tail)`, `Nil` (sentinel). Convert `(a b c)` into `Pair(a, Pair(b, Pair(c, Nil)))`. Raises `ParseError` on unbalanced parens.

## evaluator-core

`src/minischeme/evaluator.py`. `Evaluator` class with method `eval(expr: SExpr, env: Environment) -> Value | TailCall`. Dispatches on expr type:
- `Atom(int|float|str|bool)` → return literal
- `Symbol(name)` → `env.get(name)`
- `Pair(head, tail)`: depends on head; special-forms chunk extends this. For now, only literal evaluation. Later chunks add lambda/if/etc.

Public driver `run(exprs: list[SExpr], env: Environment) -> Value | None` — evaluates each top-level form, returns the last value.

## special-forms

Extends `evaluator.py` with handling for: `quote`, `if`, `cond`, `let`, `lambda` (constructs a `Closure` capturing current env), `define`, `set!`, `begin`. Implemented as branches in the `Pair` case of `eval()` keyed off `head.name`. **Reuses** the Environment, Value, SExpr types — no new types here. Tests cover each form's happy path + error path.

## builtins-arith

`src/minischeme/builtins/arith.py`. Defines `+ - * / % = < > <= >= and or not` as `Builtin` instances. Registers them via `register(env: Environment) -> None` which sets each into env. Type-checks arguments (raises `TypeError` for non-numeric where appropriate). Handles int/float promotion.

## builtins-list

`src/minischeme/builtins/listops.py`. `list cons car cdr append length map filter reduce`. Registered via the same `register(env)` pattern. `map`/`filter`/`reduce` take a `Closure` arg and call back into the evaluator — must take an evaluator reference (passed at registration time).

## builtins-string

`src/minischeme/builtins/strings.py`. `concat substring string-length string->list`. `register(env)` pattern.

## builtins-io

`src/minischeme/builtins/io.py`. `print println read-line apply`. `apply` invokes the evaluator (similar to map/filter — needs evaluator reference). `read-line` reads from `sys.stdin` (mockable for tests).

## tail-calls

Modifies `evaluator.py` to: (a) return `TailCall(closure, args)` instead of recursively evaluating the body in the call dispatch case; (b) wrap `eval()` callers in a trampoline that unwraps `TailCall` results in a loop. Verified by `(define (loop n) (if (= n 0) 'done (loop (- n 1))))` returning `'done` for n=10000 without stack overflow.

## error-handling

Adds `try` and `throw` special forms to `evaluator.py`. `throw` raises `UserError(value)`. `try` evaluates its body; on `UserError` invokes the handler with the thrown value. Test: `(try (throw 'err) (lambda (e) e))` → `'err`.

## modules

Adds `load` form. `(load "path/to/file.scm")` reads the file, lexes/parses/evaluates it in the CURRENT environment (not isolated — single-file module semantics for v1). Tested via fixture file in tests/.

## repl

`src/minischeme/repl.py`. `run_repl(env: Environment) -> None` — reads lines from stdin, lexes/parses/evaluates each, prints result. Handles multi-line input by counting parens until balanced. Uses `value_repr` for output.

## cli

`src/minischeme/cli.py`. `main(argv: list[str] | None = None) -> int`. Argparse: positional `file` (optional — REPL mode if omitted), `--help`, `--version`. Wires up: file mode → tokenize → parse → run; REPL mode → `run_repl(env)`. `__main__.py` calls `main()`.

## integration-examples

`tests/examples/` directory with `factorial.scm`, `closures.scm`, `tail_recursive_loop.scm`, `throw_catch.scm` and matching `tests/test_examples.py` that runs each via subprocess and checks output. This chunk EXISTS to verify the integration_gates' acceptance scenarios, not to add language features.

## Data model

Single in-memory environment chain. No persistence. No GC tuning (relies on Python's GC). No FFI.

## External dependencies

Runtime: pure Python stdlib (sqlite3 not used). Dev: pytest, pytest-cov, ruff (already in plugin venv).
```

- [ ] **Step 4.2: Write `chunks.yaml`**

Write to `/home/flip/Development/skillgoid-test/minischeme/.skillgoid/chunks.yaml`:

```yaml
chunks:
  - id: scaffold
    description: "Project skeleton: pyproject.toml, src layout, smoke test."
    language: python
    gate_ids: [lint, import_clean]
    paths:
      - "pyproject.toml"
      - "src/minischeme/__init__.py"
      - "src/minischeme/__main__.py"
      - "tests/__init__.py"
      - "tests/test_smoke.py"

  - id: errors
    description: "Error type hierarchy: MinischemeError + 6 subclasses."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [scaffold]
    paths:
      - "src/minischeme/errors.py"
      - "tests/test_errors.py"

  - id: values
    description: "Value protocol: Nil, Closure, Builtin, TailCall + type-check helpers."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [scaffold]
    paths:
      - "src/minischeme/values.py"
      - "tests/test_values.py"

  - id: lexer
    description: "Tokenizer with TokenType enum and Token dataclass."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [errors]
    paths:
      - "src/minischeme/lexer.py"
      - "tests/test_lexer.py"

  - id: environment
    description: "Lexical scope chain: Environment.get/set/define/extend."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [errors, values]
    paths:
      - "src/minischeme/environment.py"
      - "tests/test_environment.py"

  - id: parser
    description: "Recursive-descent parser; SExpr ADT (Atom, Symbol, Pair, Nil)."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [lexer, values]
    paths:
      - "src/minischeme/parser.py"
      - "tests/test_parser.py"

  - id: evaluator-core
    description: "Evaluator.eval dispatch on SExpr (atom/symbol/pair) with environment lookup."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [parser, environment, values]
    paths:
      - "src/minischeme/evaluator.py"
      - "tests/test_evaluator_core.py"

  - id: special-forms
    description: "if, cond, let, lambda, define, set!, begin, quote — extends evaluator."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [evaluator-core]
    paths:
      - "src/minischeme/evaluator.py"
      - "tests/test_special_forms.py"

  - id: builtins-arith
    description: "Arithmetic + comparison builtins. Registers into Environment."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [special-forms]
    paths:
      - "src/minischeme/builtins/__init__.py"
      - "src/minischeme/builtins/arith.py"
      - "tests/test_builtins_arith.py"

  - id: builtins-list
    description: "List operations: list, cons, car, cdr, append, length, map, filter, reduce."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [special-forms]
    paths:
      - "src/minischeme/builtins/listops.py"
      - "tests/test_builtins_list.py"

  - id: builtins-string
    description: "String operations: concat, substring, string-length, string->list."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [special-forms]
    paths:
      - "src/minischeme/builtins/strings.py"
      - "tests/test_builtins_string.py"

  - id: builtins-io
    description: "IO + apply: print, println, read-line, apply."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [special-forms]
    paths:
      - "src/minischeme/builtins/io.py"
      - "tests/test_builtins_io.py"

  - id: tail-calls
    description: "Trampoline TCO: TailCall return + driver loop unwrap."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [special-forms]
    paths:
      - "src/minischeme/evaluator.py"
      - "tests/test_tail_calls.py"

  - id: error-handling
    description: "try and throw special forms; UserError integration."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [special-forms]
    paths:
      - "src/minischeme/evaluator.py"
      - "tests/test_error_handling.py"

  - id: modules
    description: "load form: read+lex+parse+eval a file in current env."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [special-forms, builtins-io]
    paths:
      - "src/minischeme/evaluator.py"
      - "tests/test_modules.py"
      - "tests/fixtures/sample_module.scm"

  - id: repl
    description: "Interactive REPL with multi-line input handling."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [evaluator-core, lexer, parser, builtins-io]
    paths:
      - "src/minischeme/repl.py"
      - "tests/test_repl.py"

  - id: cli
    description: "Argparse CLI: file mode + REPL mode + --help, --version."
    language: python
    gate_ids: [lint, pytest_chunk, import_clean]
    depends_on: [repl, evaluator-core]
    paths:
      - "src/minischeme/cli.py"
      - "src/minischeme/__main__.py"
      - "tests/test_cli.py"

  - id: integration-examples
    description: "Example .scm programs + tests/test_examples.py running them via subprocess."
    language: python
    gate_ids: [lint, pytest_chunk]
    depends_on: [cli, tail-calls, error-handling, modules, builtins-arith, builtins-list, builtins-string, builtins-io]
    paths:
      - "tests/examples/factorial.scm"
      - "tests/examples/closures.scm"
      - "tests/examples/tail_recursive_loop.scm"
      - "tests/examples/throw_catch.scm"
      - "tests/test_examples.py"
```

- [ ] **Step 4.3: Validate chunks.yaml + compute waves**

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
cd /home/flip/Development/skillgoid-test/minischeme
python -c "
import json, yaml, jsonschema
data = yaml.safe_load(open('.skillgoid/chunks.yaml'))
schema = json.load(open('/home/flip/Development/skillgoid/skillgoid-plugin/schemas/chunks.schema.json'))
jsonschema.validate(data, schema)
print('OK')
"
echo "--- waves ---"
python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/chunk_topo.py \
  --chunks-file .skillgoid/chunks.yaml
```
Expected: `OK`, then JSON with `waves` array. **Compare the wave output to the spec's expected decomposition.** If it matches, H2 is confirmed for this DAG. If not, this is a 🔴 finding (chunk_topo bug at scale).

- [ ] **Step 4.4: Update v0.8-findings.md phase log**

Append:

```markdown
### plan
- blueprint.md written: ~280 lines, 18 module headings (one per chunk).
- chunks.yaml validated; chunk_topo wave output:
  <PASTE_WAVE_OUTPUT>
- H2 status: <confirmed | falsified — describe deviation from spec>
- H3 prep: blueprint.md is ~<N> tokens (`wc -w blueprint.md`); subagents will receive this verbatim.
```

- [ ] **Step 4.5: Commit**

```bash
cd /home/flip/Development/skillgoid-test/minischeme
git add .skillgoid/blueprint.md .skillgoid/chunks.yaml
git commit -qm "plan: minischeme blueprint + 18-chunk decomposition"
```

---

## Task 5: Wave 0 — scaffold (1 chunk, single subagent)

**Files:** none directly modified by you; subagent creates project skeleton.

- [ ] **Step 5.1: Pre-dispatch check**

Verify state:
```bash
ls /home/flip/Development/skillgoid-test/minischeme/.skillgoid/iterations/
```
Expected: empty.

- [ ] **Step 5.2: Dispatch scaffold subagent**

Use the reusable prompt template (top of plan). Fill in:
- `<CHUNK_ID>` = `scaffold`
- `<PASTE_CHUNK_YAML_BLOCK>` = the scaffold entry from chunks.yaml
- `<BLUEPRINT_SECTION_NAME>` = `## scaffold`
- `<PASTE_RETRIEVE_SUMMARY>` = active vault lessons recorded in Task 2's findings log

Invoke via single Agent() tool call. Subagent type: `general-purpose`. Model: `sonnet`.

- [ ] **Step 5.3: Verify subagent's return + commit**

Wait for return JSON. Verify:
- `iteration_file` = `.skillgoid/iterations/scaffold-001.json` (per v0.7 convention — H9 evidence)
- `gate_report_passed` = true (lint + import_clean)
- `commit_sha` exists in git log
- `files_in_commit` includes ONLY scaffold's `paths:` entries + the iteration JSON (per v0.7 scoping — H1 evidence even at width-1)

```bash
cd /home/flip/Development/skillgoid-test/minischeme
git log --oneline | head -3
git show --name-only HEAD --format=
```

- [ ] **Step 5.4: Update findings**

Append to v0.8-findings.md phase log:
```markdown
### Wave 0 — scaffold
- Filename: scaffold-001.json (H9 ✓)
- Commit scope: <list files>
- Gate result: passed | failed (<which>)
- Subagent friction observations: <list>
```

If anything notable surfaced (subagent confused about something, gate failed, commit included extra files), file as a finding under `## Findings`.

---

## Task 6: Wave 1 — errors + values (2 parallel)

**Files:** subagents create error types + value protocol.

- [ ] **Step 6.1: Pre-dispatch check**

```bash
ls /home/flip/Development/skillgoid-test/minischeme/.skillgoid/iterations/
```
Expected: only `scaffold-001.json`.

- [ ] **Step 6.2: Dispatch BOTH subagents in a single message (parallel wave)**

CRITICAL: emit both Agent() calls in the SAME assistant message so they run concurrently. This is the v0.5 wave-dispatch contract.

Subagent 1 prompt: template with `<CHUNK_ID>=errors`, blueprint section `## errors`, full chunks.yaml `errors` entry.
Subagent 2 prompt: template with `<CHUNK_ID>=values`, blueprint section `## values`, full chunks.yaml `values` entry.

Both subagent_type=`general-purpose`, model=`sonnet`.

- [ ] **Step 6.3: Wait for both returns; verify**

Each return JSON should show:
- `iteration_file` = `errors-001.json` and `values-001.json` (H9 ✓ at width 2)
- `gate_report_passed` = true
- `commit_sha` exists; `files_in_commit` = the chunk's `paths:` only + iter JSON
- `race_evidence.notes` — flock should have serialized them; both should report seeing the other's commit OR not (depending on timing)

```bash
cd /home/flip/Development/skillgoid-test/minischeme
git log --oneline | head -5
git show --name-only HEAD --format=
git show --name-only HEAD~1 --format=
```

Verify each commit contains ONLY its chunk's files. Cross-contamination = 🔴 H1 falsified at width-2 (regression — would mean the v0.7 fix didn't hold).

- [ ] **Step 6.4: Update findings**

Append phase log entry. Note: this is the first concurrent dispatch — flock behavior at width-2 is the baseline for H1.

---

## Task 7: Wave 2 — lexer + environment (2 parallel)

**Files:** subagents create lexer + environment modules.

- [ ] **Step 7.1: Pre-dispatch check** — verify wave 1 iterations exist + green.

- [ ] **Step 7.2: Dispatch BOTH in single message** (template same shape as Task 6, with `<CHUNK_ID>` of `lexer` and `environment`).

- [ ] **Step 7.3: Verify** — same as Task 6 step 3.

- [ ] **Step 7.4: Update findings.**

---

## Task 8: Wave 3 — parser (1 chunk)

**Files:** subagent creates parser.

- [ ] **Step 8.1: Pre-dispatch check** — verify wave 2 iterations exist + green.

- [ ] **Step 8.2: Dispatch parser subagent** — single Agent() call, template with `<CHUNK_ID>=parser`.

- [ ] **Step 8.3: Verify** — single-chunk wave; H10 evidence (flock degrades cleanly to no-contention).

- [ ] **Step 8.4: Update findings.**

---

## Task 9: Wave 4 — evaluator-core (1 chunk)

**Files:** subagent creates evaluator core.

- [ ] **Step 9.1: Pre-dispatch check** — verify wave 3 green.

- [ ] **Step 9.2: Dispatch evaluator-core subagent** — single Agent() call. Note: this chunk consumes parser's `SExpr` ADT and environment's `Environment` interface — H6 trigger point. If the subagent has trouble integrating, capture as evidence.

- [ ] **Step 9.3: Verify**

- [ ] **Step 9.4: Update findings.**

---

## Task 10: Wave 5 — special-forms (1 chunk)

**Files:** subagent extends evaluator.py with special-form dispatch.

- [ ] **Step 10.1: Pre-dispatch check** — verify wave 4 green. Special-forms MODIFIES the same file (`evaluator.py`) that evaluator-core created. The subagent must read the existing file first before extending.

- [ ] **Step 10.2: Dispatch** — single Agent() call.

- [ ] **Step 10.3: Verify** — `evaluator.py` modified (not overwritten); special-form tests pass alongside core tests.

- [ ] **Step 10.4: Update findings.**

---

## Task 11: Wave 6 — 4-way parallel builtins (★ HEADLINE — H1 at width 4)

**Files:** subagents create 4 builtin modules.

- [ ] **Step 11.1: Pre-dispatch check**

```bash
cd /home/flip/Development/skillgoid-test/minischeme
ls .skillgoid/iterations/
git log --oneline | head -10
ls -la .git/skillgoid-commit.lock 2>&1
```
Expected: 7 iteration files (scaffold + errors + values + lexer + environment + parser + evaluator-core + special-forms = 8). Lock file may or may not exist (it's created on demand).

- [ ] **Step 11.2: Dispatch ALL 4 SUBAGENTS in a single message**

THIS IS THE EXPERIMENT'S HEADLINE. Emit four Agent() tool calls in ONE assistant message. They will run concurrently, all attempting to git_iter_commit at roughly the same time, hammering `_commit_lock` at width 4.

Templates:
- `<CHUNK_ID>=builtins-arith`, blueprint section `## builtins-arith`
- `<CHUNK_ID>=builtins-list`, blueprint section `## builtins-list`
- `<CHUNK_ID>=builtins-string`, blueprint section `## builtins-string`
- `<CHUNK_ID>=builtins-io`, blueprint section `## builtins-io`

Each subagent_type=`general-purpose`, model=`sonnet`.

- [ ] **Step 11.3: Wait for ALL FOUR returns**

Even if some return faster, wait for the slowest. Don't proceed.

- [ ] **Step 11.4: VERIFY DISJOINT COMMITS — the H1 acid test**

```bash
cd /home/flip/Development/skillgoid-test/minischeme
echo "=== last 4 commits ==="
git log --oneline | head -4
echo "=== commit-by-commit file lists ==="
for c in $(git log --pretty=%H | head -4); do
  echo "--- $c ($(git show -s --format=%s $c)) ---"
  git show --name-only $c --format=
done
```

For each of the 4 commits:
- Commit message should match `iter 1 of chunk builtins-{arith,list,string,io} (passed)`
- Commit's files should be ONLY that chunk's `paths:` + the iteration JSON
- NO files from any other builtin chunk should appear

If ANY commit contains another builtin's file → **🔴 H1 falsified at width 4. STOP. This is the headline finding.**

If all 4 commits are clean → **✅ H1 confirmed at width 4. Major v0.8 datapoint.**

- [ ] **Step 11.5: Verify race evidence in subagent reports**

Look at each subagent's `race_evidence.siblings_present_at_dir_scan`. If subagent N saw siblings, the lock-acquire-then-scan worked. If none saw siblings, dispatch was perfectly serialized despite parallel intent (less likely).

- [ ] **Step 11.6: Update findings — make this the headline phase entry**

Append a substantial phase log entry for Wave 6 with:
- All 4 commit SHAs and their file lists
- Whether any cross-contamination occurred
- Race evidence summary
- H1, H10 status update in the Hypotheses tracker

---

## Task 12: Stop-or-continue checkpoint after Wave 6

**Files:** none modified.

- [ ] **Step 12.1: Evaluate stopping criteria from spec**

Per spec section "Stopping criteria":
1. Wave 6 completed successfully → STOP and proceed to Task 17 (retrospect).
2. 🔴 finding(s) accumulated → STOP and retrospect.
3. 5+ 🟡 findings → STOP and retrospect.
4. Wave 10 completes → STOP and retrospect.
5. 3+ chunks budget-exhausted → STOP and retrospect.

If criterion 1 fired (Wave 6 clean), the experiment's headline is decided. **Strongly recommended: STOP here and skip to Task 17.**

If you have remaining curiosity / budget AND no stop trigger, continue to Task 13.

- [ ] **Step 12.2: Document the choice in findings**

Append:
```markdown
### Wave 6 stopping checkpoint
- H1 status: <confirmed/falsified at width 4>
- Findings count: <N🔴, M🟡, K🟢>
- Decision: STOP / CONTINUE
- Rationale: <one sentence>
```

If STOP: skip to Task 17. If CONTINUE: proceed to Task 13.

---

## Task 13: Wave 7 — tail-calls + error-handling (2 parallel) — CONDITIONAL

Skip if Task 12 chose STOP.

**Files:** subagents extend `evaluator.py` for TCO and try/throw.

NOTE: Both chunks modify the same file (`evaluator.py`). Their `paths:` declarations in chunks.yaml correctly list `evaluator.py` for both. With v0.7's flock + scoped commit, both commits should successfully include `evaluator.py` (each commit's diff being its own changes).

This is a MORE STRINGENT H1 test than Wave 6 — Wave 6's chunks touched disjoint files. Wave 7's chunks touch the SAME file. If git's optimistic concurrency holds, both commits land cleanly with each chunk's modifications. If it doesn't, one commit's diff contains both chunks' changes (or worse, one commit fails).

- [ ] **Step 13.1: Pre-dispatch check**

- [ ] **Step 13.2: Dispatch BOTH in single message**

- [ ] **Step 13.3: Verify**

```bash
cd /home/flip/Development/skillgoid-test/minischeme
git log --oneline | head -3
echo "--- diffs ---"
for c in $(git log --pretty=%H | head -2); do
  echo "=== $c ==="
  git show --stat $c
done
```

Each commit should show `evaluator.py` in its file list with its OWN diff. If both commits show identical diffs to evaluator.py → they raced; one staged the other's changes. 🔴 finding (extension to H1).

- [ ] **Step 13.4: Update findings.**

---

## Task 14: Wave 8 — modules (1 chunk) — CONDITIONAL

Skip if STOP chosen.

- [ ] **Step 14.1: Pre-dispatch check.**
- [ ] **Step 14.2: Dispatch single subagent.**
- [ ] **Step 14.3: Verify.**
- [ ] **Step 14.4: Update findings.**

---

## Task 15: Wave 9 — repl + cli (2 parallel) — CONDITIONAL

Skip if STOP chosen.

- [ ] **Step 15.1: Pre-dispatch check.**
- [ ] **Step 15.2: Dispatch BOTH in single message.**
- [ ] **Step 15.3: Verify.**
- [ ] **Step 15.4: Update findings.**

---

## Task 16: Wave 10 — integration-examples (1 chunk) — CONDITIONAL

Skip if STOP chosen.

- [ ] **Step 16.1: Pre-dispatch check** — confirm 17 prior chunks complete.

- [ ] **Step 16.2: Dispatch integration-examples subagent.**

- [ ] **Step 16.3: Verify.**

- [ ] **Step 16.4: If integration completes, run integration_gates manually**

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
cd /home/flip/Development/skillgoid-test/minischeme
python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/measure_python.py \
  --project /home/flip/Development/skillgoid-test/minischeme \
  --criteria-stdin <<'EOF' | python -m json.tool
gates:
  - id: cli_help
    type: cli-command-runs
    command: ["python", "-m", "minischeme", "--help"]
    expect_exit: 0
    expect_stdout_match: "usage:"
    env:
      PYTHONPATH: "src"
  - id: cli_eval_smoke
    type: run-command
    command:
      - "bash"
      - "-c"
      - |
        set -euo pipefail
        echo '(println (+ 1 2))' > /tmp/minischeme_smoke.scm
        OUT=$($SKILLGOID_PYTHON -m minischeme /tmp/minischeme_smoke.scm)
        echo "$OUT" | grep -q "^3$"
    expect_exit: 0
    env:
      PYTHONPATH: "src"
  - id: cov
    type: coverage
    target: "minischeme"
    min_percent: 80
    compare_to_baseline: false
EOF
```

If all 3 integration gates pass → minischeme actually works end-to-end. Bonus.

- [ ] **Step 16.5: Update findings + write integration result.**

---

## Task 17: Retrospect + findings synthesis

**Files:**
- Create: `/home/flip/Development/skillgoid-test/minischeme/.skillgoid/retrospective.md`
- Modify: `/home/flip/Development/skillgoid-test/v0.8-findings.md` (synthesis section)
- Append one line to `~/.claude/skillgoid/metrics.jsonl`

- [ ] **Step 17.1: Run metrics_append for the experiment**

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
python /home/flip/Development/skillgoid/skillgoid-plugin/scripts/metrics_append.py \
  --skillgoid-dir /home/flip/Development/skillgoid-test/minischeme/.skillgoid \
  --slug minischeme-stress
tail -1 ~/.claude/skillgoid/metrics.jsonl
```
Expected: a JSON line with chunks=18, total_iterations=<N>, language=python, etc.

- [ ] **Step 17.2: Write `minischeme/.skillgoid/retrospective.md`**

Same shape as taskbridge's retrospective. Include:
- Outcome (success / partial-after-wave-X / aborted-after-N-findings)
- Hypotheses table updated with confirmed/falsified status for each H1–H10
- Headline findings (the 1-3 most important)
- v0.8 prioritization recommendation analogous to v0.7's

- [ ] **Step 17.3: Synthesize v0.8-findings.md**

Append a `## Synthesis` section near the end that:
- Lists every finding's severity and which hypothesis it falsified
- Ranks v0.8 priorities by ROI (same format as v0.7's "in descending ROI order")
- Calls out non-priorities (hypotheses confirmed = items NOT to spec for v0.8)
- Method note acknowledging same-driver bias

- [ ] **Step 17.4: Commit retrospective**

```bash
cd /home/flip/Development/skillgoid-test/minischeme
git add .skillgoid/retrospective.md
git commit -qm "retrospect: minischeme stress run — v0.8 findings synthesized"
```

Note: the v0.8-findings.md and metrics.jsonl files live OUTSIDE the project tree (in skillgoid-test/ and ~/.claude/ respectively); they're not committed in the project's git repo.

- [ ] **Step 17.5: Final report to the orchestrating session**

Summarize:
- Stop trigger that fired
- Hypotheses status table
- Top 3 v0.8 priorities by ROI
- File pointers to retrospective + findings

---

## Self-review checklist (done before user review)

- [x] Every spec section maps to at least one task: project setup (Task 1), retrieve (Task 2.1), clarify (Task 2), feasibility (Task 3), plan (Task 4), waves 0-10 (Tasks 5-16), retrospect (Task 17). Stopping-criteria evaluation explicit at Task 12.
- [x] No "TBD"/"TODO"/"implement later" placeholders.
- [x] Reusable subagent prompt template defined once, referenced by every wave-dispatch task — DRY.
- [x] Each wave-dispatch task explicitly says "single message, multiple Agent() calls" so the executor doesn't accidentally serialize.
- [x] Verification commands (git log, file inspection) written explicitly for each wave so observation is uniform.
- [x] Findings-log update is a step in every phase — never deferred.
- [x] Hypotheses (H1-H10) referenced at the points where they get evidence.
- [x] Stopping criteria explicitly evaluated at Task 12; conditional tasks 13-16 marked "skip if STOP."
- [x] H1 acid test (4-way parallel commits) is the headline of Task 11 with explicit go/no-go criteria.
