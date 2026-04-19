# Self-Authored Gates Phase 1.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden `/skillgoid:synthesize-gates` grounding so the synthesis subagent has less inference surface. Add two ground sources: (1) pyproject `[tool.*]` section parsing and (2) one-level wrapper-script follow for CI `run:` steps.

**Architecture:** Purely additive to `scripts/synthesize/ground_analogue.py`. Two new parser functions; both are wired into `extract_observations` alongside the existing pytest-testpaths parser and workflow-steps parser. No schema changes. No downstream changes (`synthesize.py` and `write_criteria.py` are untouched). The `Observation` dataclass shape is unchanged; new observations just use more specific `observed_type` values than `run-command`.

**Tech Stack:** Python 3.11+ stdlib (`tomllib`, `pathlib`, `shlex`), pyyaml (existing), pytest. No new dependencies.

**Spec:** This plan is self-contained. It was written after dogfooding Phase 1 against `encode/httpx` on 2026-04-19; the findings are the de-facto spec and are recorded below.

**Motivation (from dogfood):**

Running the Phase 1 pipeline against `encode/httpx` with a URL-shortener goal surfaced two grounding gaps:

1. httpx wraps its CI commands in opaque shell scripts (`scripts/test`, `scripts/check`, `scripts/coverage`). The classifier saw the wrapper name, defaulted to `run-command`, and the subagent then *promoted* those to typed `pytest`/`ruff` gates based on goal context. Plausible, but not grounded in observation.
2. httpx has rich `[tool.pytest.ini_options]`, `[tool.ruff.lint]`, `[tool.mypy]` (strict=true), and `[tool.coverage.run]` sections in `pyproject.toml`. The existing parser only looks at `[tool.pytest.ini_options].testpaths` — a narrow slice. Everything else was dropped.

Deeper grounding shrinks the subagent's inference budget and converts "plausible guess" provenance into "literal config" provenance.

**What this plan does NOT do:**

- No context7 grounding (Phase 2).
- No curated template fallback (Phase 2).
- No oracle validation — gates still ship with `validated: none (Phase 1: oracle validation deferred)` (Phase 2).
- No change to `clarify`, `build`, or any other skill.
- No recursion into wrapper scripts that call other wrapper scripts (max depth = 1; keeps grounding deterministic and auditable).

---

## File Structure

**New files:**
- `tests/fixtures/synthesize/mini-flask-demo/scripts/check` — wrapper-script fixture (new fixture file)
- `tests/fixtures/synthesize/mini-flask-demo/scripts/test` — wrapper-script fixture (new fixture file)

**Modified files:**
- `scripts/synthesize/ground_analogue.py` — add `parse_pyproject_tool_sections()`, `follow_wrapper_script()`, wire both into `extract_observations`
- `tests/test_ground_analogue.py` — new tests for each function + integration
- `tests/fixtures/synthesize/mini-flask-demo/.github/workflows/ci.yml` — append a wrapper-calling step (if file exists; otherwise create)
- `tests/fixtures/synthesize/mini-flask-demo/pyproject.toml` — ensure it declares `[tool.pytest.ini_options]` + `[tool.ruff]` + `[tool.mypy]` + `[tool.coverage.run]` so the tool-section parser has something to find (it already declares pytest; we will add ruff/mypy/coverage)
- `skills/synthesize-gates/SKILL.md` — update Phase 1 limitations list (remove now-addressed gaps; keep remaining Phase 2 gaps)
- `tests/test_synthesize_e2e.py` — extend the e2e fixture expectations to include the new observations

**Plugin version bump:**
- `.claude-plugin/plugin.json` — bump the existing version. The current `"version"` is `0.8.0`; Phase 1 did not bump it. Phase 1.5 should bump to `0.9.0` (minor bump reflects the new user-facing synthesize-gates skill shipped across Phase 1 + 1.5).

---

## Tasks

### Task 1: pyproject `[tool.*]` section parser

Add a function that walks the four recognized top-level tool sections in `pyproject.toml` and emits one inferred-command-and-type pair per section found. This is separate from the existing `parse_pyproject_test_command` (which is pytest-testpaths-specific); the two can coexist and the existing dedup handles any overlap.

**Files:**
- Modify: `scripts/synthesize/ground_analogue.py`
- Test: `tests/test_ground_analogue.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ground_analogue.py`:

```python
def test_parse_pyproject_tool_sections_pytest_only(tmp_path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.pytest.ini_options]\n"
        'addopts = "-rxXs"\n'
    )
    out = parse_pyproject_tool_sections(pp)
    assert out == [("pytest", "pytest", "tool.pytest.ini_options")]


def test_parse_pyproject_tool_sections_all_four(tmp_path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.pytest.ini_options]\n"
        'addopts = "-rxXs"\n'
        "[tool.ruff.lint]\n"
        'select = ["E", "F"]\n'
        "[tool.mypy]\n"
        "strict = true\n"
        "[tool.coverage.run]\n"
        'omit = ["venv/*"]\n'
    )
    out = parse_pyproject_tool_sections(pp)
    # Order is stable: pytest, ruff, mypy, coverage
    assert out == [
        ("pytest", "pytest", "tool.pytest.ini_options"),
        ("ruff", "ruff check .", "tool.ruff.lint"),
        ("mypy", "mypy .", "tool.mypy"),
        ("coverage", "coverage run -m pytest", "tool.coverage.run"),
    ]


def test_parse_pyproject_tool_sections_ruff_top_level(tmp_path):
    # [tool.ruff] with no sub-section still counts as ruff configured.
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.ruff]\n"
        "line-length = 100\n"
    )
    out = parse_pyproject_tool_sections(pp)
    assert out == [("ruff", "ruff check .", "tool.ruff")]


def test_parse_pyproject_tool_sections_missing_returns_empty(tmp_path):
    pp = tmp_path / "pyproject.toml"
    assert parse_pyproject_tool_sections(pp) == []


def test_parse_pyproject_tool_sections_malformed_returns_empty(tmp_path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text("not valid toml =[[[\n")
    assert parse_pyproject_tool_sections(pp) == []


def test_parse_pyproject_tool_sections_no_recognized_tools(tmp_path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.poetry]\n"
        'name = "demo"\n'
        "[tool.black]\n"
        'line-length = 88\n'
    )
    # Neither poetry nor black is in our recognized set.
    assert parse_pyproject_tool_sections(pp) == []
```

Add `parse_pyproject_tool_sections` to the imports at the top of the test file alongside the existing imports from `scripts.synthesize.ground_analogue`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ground_analogue.py -v -k "tool_sections"`
Expected: all 6 tests FAIL with `ImportError: cannot import name 'parse_pyproject_tool_sections'` (or similar) — the function does not exist yet.

- [ ] **Step 3: Implement `parse_pyproject_tool_sections`**

In `scripts/synthesize/ground_analogue.py`, below the existing `parse_pyproject_test_command` function, add:

```python
# Ordered: pytest, ruff, mypy, coverage. The tuple is (section-keys-to-check,
# tool-name, inferred-command). We check the first matching section key and
# stop — `tool.ruff.lint` wins over a bare `tool.ruff` when both exist, but
# either alone is enough.
_PYPROJECT_TOOL_SPECS: list[tuple[tuple[str, ...], str, str]] = [
    (("tool", "pytest", "ini_options"), "pytest", "pytest"),
    (("tool", "ruff", "lint"), "ruff", "ruff check ."),
    (("tool", "ruff"), "ruff", "ruff check ."),
    (("tool", "mypy"), "mypy", "mypy ."),
    (("tool", "coverage", "run"), "coverage", "coverage run -m pytest"),
]


def parse_pyproject_tool_sections(
    pyproject: Path,
) -> list[tuple[str, str, str]]:
    """Return (tool, inferred_command, section_name) for each recognized
    [tool.*] section found in pyproject.toml.

    One entry per tool (deduped at call site even if multiple section keys match).
    Result order: pytest, ruff, mypy, coverage. Returns [] if pyproject missing
    or malformed.
    """
    if not pyproject.exists():
        return []
    try:
        import tomllib
    except ImportError:  # pragma: no cover — Python <3.11 not supported
        return []
    try:
        data = tomllib.loads(pyproject.read_text())
    except tomllib.TOMLDecodeError:
        return []

    found: list[tuple[str, str, str]] = []
    seen_tools: set[str] = set()
    for keys, tool, command in _PYPROJECT_TOOL_SPECS:
        if tool in seen_tools:
            continue
        cursor: object = data
        for key in keys:
            if not isinstance(cursor, dict) or key not in cursor:
                cursor = None
                break
            cursor = cursor[key]
        if cursor is None:
            continue
        section_name = ".".join(keys)
        found.append((tool, command, section_name))
        seen_tools.add(tool)
    return found
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ground_analogue.py -v -k "tool_sections"`
Expected: 6 PASS.

Also run the full ground_analogue test file to confirm no regression:
Run: `.venv/bin/pytest tests/test_ground_analogue.py -v`
Expected: all existing tests still PASS (15+ tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/synthesize/ground_analogue.py tests/test_ground_analogue.py
git commit -m "synthesize: pyproject [tool.*] section parser

Adds parse_pyproject_tool_sections() which walks [tool.pytest], [tool.ruff],
[tool.mypy], and [tool.coverage] sections in pyproject.toml and emits one
(tool, inferred-command, section-path) tuple per section found.

Groundwork for Phase 1.5 — will be wired into extract_observations in the
next commit. Coexists with the existing pytest-testpaths parser; dedup at
extract_observations resolves any overlap.

Phase 1.5 of self-authored gates (dogfood on encode/httpx surfaced the
gap: rich [tool.*] config was dropped on the floor).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Wire pyproject tool sections into `extract_observations`

Call the new parser inside `extract_observations` and emit one `Observation` per recognized section. Ref is `<repo>/pyproject.toml#<section>`; context names the section.

**Files:**
- Modify: `scripts/synthesize/ground_analogue.py:117-165` (the `extract_observations` body)
- Test: `tests/test_ground_analogue.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_ground_analogue.py`:

```python
def test_extract_observations_emits_from_pyproject_tool_sections(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'addopts = "-rxXs"\n'
        "[tool.ruff.lint]\n"
        'select = ["E"]\n'
        "[tool.mypy]\n"
        "strict = true\n"
    )
    obs = extract_observations(repo)
    # Should include one observation per tool section, in order.
    types_seen = [o.observed_type for o in obs]
    assert "pytest" in types_seen
    assert "ruff" in types_seen
    assert "mypy" in types_seen
    # Each pyproject observation refs the section path
    pyproject_obs = [o for o in obs if "pyproject.toml" in o.ref]
    refs = {o.ref for o in pyproject_obs}
    assert "demo/pyproject.toml#tool.pytest.ini_options" in refs
    assert "demo/pyproject.toml#tool.ruff.lint" in refs
    assert "demo/pyproject.toml#tool.mypy" in refs
    # Context names the section
    for o in pyproject_obs:
        assert "pyproject.toml" in o.context
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ground_analogue.py -v -k "emits_from_pyproject_tool_sections"`
Expected: FAIL — the new observations aren't in `obs` yet.

- [ ] **Step 3: Update `extract_observations`**

In `scripts/synthesize/ground_analogue.py`, locate `extract_observations` at line ~117 and insert the new source block between existing "Source 1" (testpaths) and "Source 2" (workflow steps):

```python
    # Source 1b: pyproject.toml tool sections (pytest-testpaths-independent)
    for tool, command, section in parse_pyproject_tool_sections(
        repo / "pyproject.toml"
    ):
        observations.append(Observation(
            source="analogue",
            ref=f"{repo_name}/pyproject.toml#{section}",
            command=command,
            context=f"pyproject.toml [{section}] section declares {tool} configured",
            observed_type=tool,
        ))
```

Note: this runs BEFORE "Source 2" (workflow steps) so dedup prefers the config-grounded observation if a workflow later emits the same command with the same type.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ground_analogue.py -v`
Expected: all tests PASS, including the new integration test.

- [ ] **Step 5: Commit**

```bash
git add scripts/synthesize/ground_analogue.py tests/test_ground_analogue.py
git commit -m "synthesize: emit pyproject [tool.*] observations

Wires parse_pyproject_tool_sections into extract_observations. Each
recognized [tool.*] section becomes a typed Observation with ref
'<repo>/pyproject.toml#<section>' and context naming the section.

Emitted before workflow-step observations so the config-grounded
observation wins on (command, type) dedup.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Wrapper-script follow parser

Add a function that, given a script path relative to a repo root, reads the script (max 100 lines, safety cap), walks each non-comment non-blank line, and yields command strings. The caller decides whether to classify them.

**Files:**
- Modify: `scripts/synthesize/ground_analogue.py`
- Test: `tests/test_ground_analogue.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ground_analogue.py`:

```python
def test_follow_wrapper_script_extracts_commands(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    script.write_text(
        "#!/bin/sh\n"
        "set -e\n"
        "\n"
        "# Run the suite\n"
        "pytest tests/\n"
        "ruff check .\n"
    )
    out = follow_wrapper_script(script, repo)
    assert out == ["pytest tests/", "ruff check ."]


def test_follow_wrapper_script_strips_prefix_substitutions(tmp_path):
    # Real-world httpx pattern: ${PREFIX}pytest "$@"
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    script.write_text(
        "#!/bin/sh\n"
        'export PREFIX=""\n'
        '${PREFIX}coverage run -m pytest "$@"\n'
        '${PREFIX}ruff check .\n'
    )
    out = follow_wrapper_script(script, repo)
    # Prefix substitution is stripped so the classifier can see the real head
    assert out == ['coverage run -m pytest "$@"', "ruff check ."]


def test_follow_wrapper_script_skips_shell_builtins(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    script.write_text(
        "#!/bin/sh\n"
        "export FOO=bar\n"
        "set -ex\n"
        "if [ -z $X ]; then\n"
        "  pytest\n"
        "fi\n"
        "cd ..\n"
    )
    out = follow_wrapper_script(script, repo)
    # Only `pytest` survives — export/set/if/fi/cd are filtered
    assert out == ["pytest"]


def test_follow_wrapper_script_missing_returns_empty(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    assert follow_wrapper_script(repo / "nope", repo) == []


def test_follow_wrapper_script_rejects_path_outside_repo(tmp_path):
    # Security: script must be inside repo_root
    repo = tmp_path / "demo"
    repo.mkdir()
    outside = tmp_path / "outside.sh"
    outside.write_text("#!/bin/sh\npytest\n")
    assert follow_wrapper_script(outside, repo) == []


def test_follow_wrapper_script_caps_at_100_lines(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    script = repo / "scripts" / "test"
    body = "#!/bin/sh\n" + "\n".join(f"cmd_{i}" for i in range(200)) + "\n"
    script.write_text(body)
    out = follow_wrapper_script(script, repo)
    # 100-line cap includes the shebang line
    assert len(out) <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ground_analogue.py -v -k "wrapper_script"`
Expected: all 6 tests FAIL with `ImportError` — the function does not exist yet.

- [ ] **Step 3: Implement `follow_wrapper_script`**

In `scripts/synthesize/ground_analogue.py`, below `_classify_command`, add:

```python
import re

# Lines we ignore in wrapper scripts — shell builtins and flow control.
_WRAPPER_IGNORE_HEADS = frozenset({
    "export", "set", "unset", "cd", "if", "then", "else", "elif", "fi",
    "for", "do", "done", "while", "case", "esac", "trap", "source", ".",
    "alias", "function", "local", "readonly", "return", "shift", "test",
    "[", "[[", "exit",
})

_PREFIX_SUB_RE = re.compile(r"^\$\{[A-Z_]+\}")


def follow_wrapper_script(script: Path, repo_root: Path) -> list[str]:
    """Read a shell wrapper script and return the real command strings in it.

    Returns [] if the script does not exist, is outside repo_root, is
    unreadable, or contains no recognized commands. Reads at most 100
    lines (safety cap).

    The result is a list of command strings suitable for `_classify_command`.
    Shell builtins (export, set, if, cd, etc.) are filtered. Common prefix
    substitutions like `${PREFIX}pytest` are stripped so the classifier
    sees `pytest`.
    """
    if not script.exists() or not script.is_file():
        return []
    # Security: reject paths that resolve outside repo_root.
    try:
        script.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return []

    try:
        text = script.read_text()
    except (OSError, UnicodeDecodeError):
        return []

    out: list[str] = []
    for i, raw in enumerate(text.splitlines()):
        if i >= 100:
            break
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip a leading ${VAR} prefix substitution so the classifier can
        # see the real command head.
        stripped = _PREFIX_SUB_RE.sub("", line)
        # Strip leading `./` since that's still the same command.
        if stripped.startswith("./"):
            stripped = stripped[2:]
        head = stripped.split()[0] if stripped.split() else ""
        if head in _WRAPPER_IGNORE_HEADS:
            continue
        # Skip assignments (FOO=bar) — not a command.
        if "=" in head and head.split("=", 1)[0].replace("_", "").isalnum():
            continue
        out.append(stripped)
    return out
```

Note: add `import re` at the top of the file if it is not already imported.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ground_analogue.py -v -k "wrapper_script"`
Expected: 6 PASS.

Also run the full test file to confirm no regression:
Run: `.venv/bin/pytest tests/test_ground_analogue.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/synthesize/ground_analogue.py tests/test_ground_analogue.py
git commit -m "synthesize: wrapper-script follow parser

Adds follow_wrapper_script() which reads a shell wrapper (up to 100 lines),
strips shell builtins and prefix substitutions like \${PREFIX}, and returns
the real command strings. Security: rejects paths outside the repo root.

This is the pure parser — integration into extract_observations follows
in the next commit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Wire wrapper-script follow into `extract_observations`

When a workflow-step command's head resolves to a file inside the repo, follow that wrapper one level and emit observations for each command we find, with refs pointing at the wrapper script (not the workflow).

**Files:**
- Modify: `scripts/synthesize/ground_analogue.py:extract_observations`
- Test: `tests/test_ground_analogue.py`

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_ground_analogue.py`:

```python
def test_extract_observations_follows_wrapper_scripts(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()

    # Wrapper script that runs pytest + ruff
    (repo / "scripts").mkdir()
    (repo / "scripts" / "test").write_text(
        "#!/bin/sh\n"
        "pytest tests/\n"
        "ruff check .\n"
    )

    # CI workflow that calls the wrapper
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "name: ci\n"
        "on: [push]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: scripts/test\n"
    )

    obs = extract_observations(repo)
    types_seen = [o.observed_type for o in obs]

    # We should see typed pytest + ruff observations, not just run-command
    assert "pytest" in types_seen
    assert "ruff" in types_seen

    # The followed observations ref the wrapper script, not the workflow
    pytest_obs = [o for o in obs if o.observed_type == "pytest"]
    assert any(o.ref.endswith("scripts/test") for o in pytest_obs)

    # Context explains the wrapper follow
    wrapper_obs = [o for o in obs if "wrapper" in o.context.lower()]
    assert wrapper_obs, "expected at least one wrapper-derived observation"


def test_extract_observations_wrapper_follow_is_one_level_deep(tmp_path):
    # scripts/test calls scripts/inner which would call pytest, but we
    # deliberately don't recurse — only scripts/test is followed.
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    (repo / "scripts" / "test").write_text(
        "#!/bin/sh\n"
        "scripts/inner\n"
    )
    (repo / "scripts" / "inner").write_text(
        "#!/bin/sh\n"
        "pytest\n"
    )
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "name: ci\n"
        "on: [push]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: scripts/test\n"
    )

    obs = extract_observations(repo)
    # We observe `scripts/inner` as a run-command (from scripts/test), but
    # we do NOT recurse into scripts/inner to find the pytest call.
    types_seen = [o.observed_type for o in obs]
    # No pytest (only scripts/inner as run-command from the depth-1 follow)
    assert "pytest" not in types_seen
    # scripts/inner is observed as a command head
    commands = [o.command for o in obs]
    assert any("scripts/inner" in c for c in commands)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ground_analogue.py -v -k "wrapper"`
Expected: both tests FAIL — wrapper follow is not wired into `extract_observations` yet.

- [ ] **Step 3: Update `extract_observations` to follow wrappers**

In `scripts/synthesize/ground_analogue.py`, inside the `extract_observations` function, modify the workflow-step loop. Replace the current workflow-step block with:

```python
    # Source 2: GitHub Actions workflow run-steps.
    # For each step, classify the command. If the head resolves to a file
    # inside the repo (a wrapper script), follow it one level and emit
    # observations for each command we find, with refs pointing at the wrapper.
    workflows_dir = repo / ".github" / "workflows"
    if workflows_dir.exists():
        workflow_files = list(workflows_dir.glob("*.yml")) + list(
            workflows_dir.glob("*.yaml")
        )
        for wf in sorted(workflow_files):
            for step_cmd in parse_workflow_steps(wf):
                otype = _classify_command(step_cmd)
                if otype is None:
                    continue
                wf_ref = f"{repo_name}/.github/workflows/{wf.name}"

                # Try to follow a wrapper. The head is the token after an
                # optional `./`. If that resolves to a file in repo, read it.
                head = step_cmd.strip().split()[0] if step_cmd.strip() else ""
                candidate = head[2:] if head.startswith("./") else head
                candidate_path = repo / candidate
                wrapper_cmds = (
                    follow_wrapper_script(candidate_path, repo)
                    if candidate and candidate_path.is_file()
                    else []
                )

                if wrapper_cmds:
                    wrapper_ref = f"{repo_name}/{candidate}"
                    for inner in wrapper_cmds:
                        inner_type = _classify_command(inner)
                        if inner_type is None:
                            continue
                        observations.append(Observation(
                            source="analogue",
                            ref=wrapper_ref,
                            command=inner,
                            context=f"CI wrapper script (called from {wf.name})",
                            observed_type=inner_type,
                        ))
                else:
                    observations.append(Observation(
                        source="analogue",
                        ref=wf_ref,
                        command=step_cmd,
                        context="CI workflow step",
                        observed_type=otype,
                    ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ground_analogue.py -v`
Expected: all tests PASS (including existing non-wrapper workflow tests — none should have regressed).

- [ ] **Step 5: Commit**

```bash
git add scripts/synthesize/ground_analogue.py tests/test_ground_analogue.py
git commit -m "synthesize: follow CI wrapper scripts one level deep

extract_observations now checks whether each workflow step's command head
resolves to a file inside the repo. If it does, the wrapper is read via
follow_wrapper_script and its inner commands are emitted as observations
with refs pointing at the wrapper script itself (not the workflow YAML).

One level only — no recursion. A wrapper that calls another wrapper is
still surfaced, just as an un-followed run-command observation.

Phase 1.5 of self-authored gates. Closes the httpx-style opaque-wrapper
grounding gap found during dogfood.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Extend mini-flask-demo fixture and e2e test

Update the vendored fixture so the e2e pipeline exercises the two new code paths (tool-section and wrapper-follow). Update the e2e assertions accordingly.

**Files:**
- Modify: `tests/fixtures/synthesize/mini-flask-demo/pyproject.toml` — add `[tool.ruff]` + `[tool.mypy]` + `[tool.coverage.run]`
- Create: `tests/fixtures/synthesize/mini-flask-demo/scripts/test`
- Modify (or create): `tests/fixtures/synthesize/mini-flask-demo/.github/workflows/ci.yml` — add a step that calls `scripts/test`
- Modify: `tests/test_synthesize_e2e.py` — add an assertion that the new observation shapes appear in grounding

- [ ] **Step 1: Inspect current mini-flask-demo fixture state**

Run: `ls tests/fixtures/synthesize/mini-flask-demo/ && cat tests/fixtures/synthesize/mini-flask-demo/pyproject.toml`

Expected: lists the vendored file tree; shows current pyproject contents. Note which tool sections already exist.

- [ ] **Step 2: Extend pyproject.toml (if sections missing)**

Append (only the sections that are not already present) to `tests/fixtures/synthesize/mini-flask-demo/pyproject.toml`:

```toml
[tool.ruff]
line-length = 100

[tool.mypy]
strict = false

[tool.coverage.run]
omit = ["tests/*"]
```

- [ ] **Step 3: Create the wrapper script fixture**

Create `tests/fixtures/synthesize/mini-flask-demo/scripts/test`:

```sh
#!/bin/sh
set -e
pytest tests/
ruff check .
```

Make it executable (not strictly required for the parser — it reads the file regardless — but matches realistic fixtures):

```bash
chmod +x tests/fixtures/synthesize/mini-flask-demo/scripts/test
```

- [ ] **Step 4: Ensure CI workflow calls the wrapper**

If `tests/fixtures/synthesize/mini-flask-demo/.github/workflows/ci.yml` does not exist, create it:

```yaml
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: scripts/test
```

If it exists, read it first and append a new step `- run: scripts/test` at the end of the `steps:` list rather than replacing existing content.

- [ ] **Step 5: Update e2e test assertions**

In `tests/test_synthesize_e2e.py`, find the grounding-output assertions in the main e2e test (`test_full_pipeline_with_mocked_subagent`) and extend them so the test verifies that the new Phase 1.5 observation shapes appear:

```python
# After loading grounding.json in the e2e test, assert the Phase 1.5 shapes
observed_types = {o["observed_type"] for o in grounding["observations"]}
assert "ruff" in observed_types, "pyproject [tool.ruff] should produce ruff observation"
assert "mypy" in observed_types, "pyproject [tool.mypy] should produce mypy observation"

refs = {o["ref"] for o in grounding["observations"]}
assert any("pyproject.toml#tool." in r for r in refs), "at least one pyproject tool-section ref expected"
assert any(r.endswith("scripts/test") for r in refs), "at least one wrapper-script ref expected"
```

If the mocked subagent JSON elsewhere in the e2e test pins `provenance.ref` to a specific grounding observation, rewrite those refs to reference a ref that is guaranteed present (e.g., `{repo_name}/pyproject.toml#tool.pytest.ini_options`). The existing test dynamically pulls refs from `grounding["observations"]`, so this may already be handled.

- [ ] **Step 6: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: all tests PASS (including the e2e test with updated assertions).

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/synthesize/mini-flask-demo/ tests/test_synthesize_e2e.py
git commit -m "synthesize: exercise Phase 1.5 grounding in e2e fixture

Extends mini-flask-demo with [tool.ruff], [tool.mypy], [tool.coverage.run]
and a scripts/test wrapper called from a CI workflow step. The e2e test
now asserts that the tool-section and wrapper-follow grounding paths
both fire.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Update skill prose + version bump

Reflect the reduced Phase 1 limitations in `skills/synthesize-gates/SKILL.md` and bump the plugin version.

**Files:**
- Modify: `skills/synthesize-gates/SKILL.md` — trim the Phase 1 limitations block
- Modify: `.claude-plugin/plugin.json` — version bump

- [ ] **Step 1: Inspect current SKILL.md limitations block**

Read `skills/synthesize-gates/SKILL.md`, locate the `## Phase 1 limitations (called out for users)` section.

- [ ] **Step 2: Update the limitations list**

Replace the content of the `## Phase 1 limitations (called out for users)` section with:

```markdown
## Phase 1 limitations (called out for users)

Phase 1.5 addresses the grounding-depth gaps from the initial Phase 1
(pyproject `[tool.*]` sections are now parsed; CI wrapper scripts are
followed one level deep). The remaining Phase 2 gaps:

- All gates are labeled `validated: none (Phase 1: oracle validation deferred)`. The user is the only validator.
- No context7 grounding — only user-pointed analogues.
- No curated template fallback for cold-start projects.
- No retry on subagent output validation failure — re-run the skill if needed.

Phase 2 (planned) addresses all four.
```

- [ ] **Step 3: Bump plugin version**

Read `.claude-plugin/plugin.json`, find the `"version"` field (currently `0.8.0`), and change it to `0.9.0`. This single minor bump covers Phase 1 + Phase 1.5 since Phase 1 did not bump the manifest.

- [ ] **Step 4: Run the full suite one more time**

Run: `.venv/bin/pytest && .venv/bin/ruff check .`
Expected: all tests PASS, lint clean.

- [ ] **Step 5: Commit**

```bash
git add skills/synthesize-gates/SKILL.md .claude-plugin/plugin.json
git commit -m "synthesize: v0.9.0 — Phase 1.5 grounding depth

Bumps plugin version to 0.9.0 (covers both Phase 1 and Phase 1.5 of the
synthesize-gates skill, since Phase 1 did not bump the manifest) and
trims the Phase 1 limitations block
in skills/synthesize-gates/SKILL.md to reflect that pyproject [tool.*]
parsing and CI wrapper-script follow are now live.

Remaining Phase 2 gaps: context7, templates, oracle validation, auto-retry.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Re-dogfood against encode/httpx

Re-run the synthesis pipeline against the same analogue (`encode/httpx`) and the same test goal used in the Phase 1 dogfood. Confirm the new grounding observations change the shape of the synthesized drafts — ideally converting the earlier "type-laundered" drafts into drafts whose provenance is a `[tool.*]` section or a wrapper-script ref.

This is an exploratory smoke test, not a unit test. No commit required unless the result surfaces a bug in the code delivered above.

**Files:**
- Read-only: `/home/flip/Development/skillgoid-test/phase1-dogfood/.skillgoid/` (already set up in the Phase 1 dogfood session; the analogue clone still exists)

- [ ] **Step 1: Clean the Phase 1 dogfood artifacts**

```bash
rm -f /home/flip/Development/skillgoid-test/phase1-dogfood/.skillgoid/synthesis/grounding.json
rm -f /home/flip/Development/skillgoid-test/phase1-dogfood/.skillgoid/synthesis/drafts.json
rm -f /home/flip/Development/skillgoid-test/phase1-dogfood/.skillgoid/criteria.yaml.proposed
```

- [ ] **Step 2: Re-run Stage 1 (grounding)**

```bash
cd /home/flip/Development/skillgoid-test/phase1-dogfood && \
  /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
  /home/flip/Development/skillgoid/skillgoid-plugin/scripts/synthesize/ground.py \
  --skillgoid-dir .skillgoid \
  .skillgoid/synthesis/analogues/encode-httpx
```

Read the resulting `grounding.json`. Expected new-in-Phase-1.5 observations:
- `pytest`, `ruff`, `mypy`, `coverage` observations with refs ending in `pyproject.toml#tool.*`
- Typed observations (pytest, ruff, coverage, mypy) with refs ending in `scripts/test`, `scripts/check`, `scripts/coverage` (instead of the bare workflow refs seen in Phase 1)

- [ ] **Step 3: Dispatch the synthesis subagent with the new grounding**

Dispatch the synthesis subagent (same prompt template as Phase 1). Attach the new `grounding.json` and the existing `goal.md`. Capture its JSON output.

- [ ] **Step 4: Run Stages 2 + 4**

```bash
echo "<subagent_stdout>" | /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
  /home/flip/Development/skillgoid/skillgoid-plugin/scripts/synthesize/synthesize.py \
  --skillgoid-dir .skillgoid && \
  /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
  /home/flip/Development/skillgoid/skillgoid-plugin/scripts/synthesize/write_criteria.py \
  --skillgoid-dir .skillgoid
```

- [ ] **Step 5: Inspect `.skillgoid/criteria.yaml.proposed` and compare to Phase 1**

Expected improvements:
- pytest/ruff/mypy drafts now cite pyproject tool-section refs or wrapper-script refs — not workflow-file refs.
- The `cli-command-runs` drafts invented from goal.md may still appear (that's a separate Phase 2 concern about semantic provenance).

If a specific gate is grounded in `pyproject.toml#tool.mypy`, that is the clearest possible wins signal — it means the subagent used literal config evidence rather than plausibility-inferring from a wrapper name.

If the result does NOT show these improvements, debug before declaring Phase 1.5 done: likely the grounding is correct but the subagent prompt needs tuning to prefer specific refs over generic ones.

- [ ] **Step 6: Record findings in the plan file**

Append a short "Dogfood 2 result" section to the bottom of *this plan file* noting what changed versus the Phase 1 dogfood. Commit the update.

---

## Risks

- **Overly aggressive wrapper-script parsing could emit noisy observations.** Mitigation: the `_WRAPPER_IGNORE_HEADS` allowlist is conservative; anything we don't recognize still becomes a typed observation, which the dedup filter then collapses.
- **`[tool.ruff]` vs `[tool.ruff.lint]`: we pick one.** The `_PYPROJECT_TOOL_SPECS` ordering means `tool.ruff.lint` is preferred if both exist; otherwise bare `tool.ruff`. Either way we emit one observation per tool. Acceptable for now; Phase 2 can inspect `lint.select` / `format` config to propose richer args.
- **Security: wrapper-script reads are bounded.** Max 100 lines, path-must-be-inside-repo check via `script.resolve().relative_to(repo_root.resolve())`. This prevents a hostile analogue from causing us to read arbitrary system files.
- **Backward compatibility.** The `Observation` shape is unchanged; existing tests that check count/order of observations must be updated to accommodate the new sources. Any flaky test counts indicate an incomplete Task-5 update.
- **Phase 1.5 does NOT fix semantic hallucination.** The dogfood finding that the subagent invented `shrink add https://example.com` with a false-evidence ref is a *Phase 2* problem (semantic provenance check in `synthesize.py`). Called out so the user doesn't expect Phase 1.5 to close it.

---

## Phase 2 follow-ups left open

Explicitly not addressed here; tracked for the Phase 2 plan:

1. **Semantic provenance check** — verify the drafted gate type is supported by the cited observation's content, not just by ref-string existence.
2. **`cli-command-runs` invention** — constrain the subagent so CLI smoke-tests can only be drafted when the project's own source declares a CLI entry point (pyproject `[project.scripts]`) that matches the command.
3. **context7 grounding** and **curated template fallback** — alternate sources for when no analogue is available.
4. **Oracle validation** — actually execute gates in a sandbox to assign `validated: clean | noisy | broken` per-gate.
5. **Auto-retry on subagent output parse failure** — single retry with the parse error message in context.
6. **Generalize language-detect across analogues** — current "first-non-unknown wins" policy is OK for one analogue, noisy for mixed repos.

---

## Dogfood 2 result (2026-04-19)

Re-ran Stage 1 + 2 + 4 against `encode/httpx` with the same URL-shortener goal used in the Phase 1 dogfood.

**Grounding comparison:**

| | Phase 1 | Phase 1.5 |
|---|---|---|
| Total observations | 6 | 24 (pre-dedup by ground.py; 9 surfaced) |
| Observations typed `run-command` only | 6 (100 %) | ~8 noisy ones from install/build/publish wrappers |
| Typed pytest/ruff/mypy/coverage | 0 | 4 (all from pyproject `[tool.*]`) + more from wrapper follow |
| Refs pointing to pyproject tool sections | 0 | 4 |
| Refs pointing to wrapper scripts | 0 | 5 (scripts/install, build, publish, check, test, coverage) |

**Synthesized drafts comparison:**

| | Phase 1 | Phase 1.5 |
|---|---|---|
| Total drafts | 4 | 6 |
| Invented `cli-command-runs` (from goal only) | 2 | 0 |
| Drafts citing pyproject refs | 0 | 3 (ruff, mypy, pytest) |
| Drafts citing wrapper-script refs | 0 | 3 (scripts/check, scripts/test, scripts/coverage) |
| Type-laundering from `run-command` | 2 (pytest, ruff inferred from wrapper name) | 0 |

**Wins:**
- Zero type-laundering. All typed gates are grounded in pyproject config or wrapper-script content.
- Zero invented `cli-command-runs`. Without a wrapper-observed `cli-command-runs` pattern, the subagent correctly omits it.
- ruff, mypy, coverage observations now cite `pyproject.toml#tool.*` refs — the clearest possible provenance.

**Remaining Phase 2 concern:**
- `coverage-report --fail-under=100` is appropriate for httpx's high test-quality bar but may be too strict for a fresh project. This is a semantic-provenance problem (the constraint transfers without adjustment). Phase 2's oracle validation would catch this by running the gate against the user's nascent project and observing failure.
- The subagent output wrapped JSON in markdown fences (not valid protocol). This is a subagent prompt-compliance issue; synthesize.py currently requires clean stdout. Phase 2 should add a strip-fences fallback in parse_subagent_output.

**Conclusion:** Phase 1.5 closes the grounding-depth gap that caused Phase 1's type-laundering. The pipeline is ready for Phase 2 (oracle validation + context7 + templates).
