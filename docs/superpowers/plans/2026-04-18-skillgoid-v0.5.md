# Skillgoid v0.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Skillgoid v0.5 — Evidence-Driven Polish. Small bundle: vault supersession tracking + feasibility scaffolding awareness + parallel chunks. Plan-refinement-mid-build is intentionally NOT included (3 real runs produced zero evidence).

**Architecture:** Two prose-only skill updates (`retrieve` + `feasibility`), one small prose+logic update (`build` — parallel wave dispatch), one new helper script (`chunk_topo.py`), optional `vault_filter.py` helper. Fully backward-compatible with v0.4.

**Tech Stack:** Python 3.11+, pytest, ruff (existing). No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-04-18-skillgoid-v0.5-evidence-driven-polish.md` (commit `f12fbef`).
**Evidence:** `~/.claude/skillgoid/metrics.jsonl` (3 lines: jyctl, taskq, mdstats). Three retrospectives in `/home/flip/Development/skillgoid-test/*/`.

---

## Repo layout changes

```
skillgoid-plugin/
├── scripts/
│   ├── chunk_topo.py                 # NEW: plan_waves() for parallel dispatch
│   ├── vault_filter.py               # NEW: parse Status: lines, filter by current plugin version
│   └── (others unchanged)
├── skills/
│   ├── build/SKILL.md                # MODIFIED: wave dispatch prose
│   ├── feasibility/SKILL.md          # MODIFIED: scaffolding awareness
│   ├── retrieve/SKILL.md             # MODIFIED: vault filter prose
│   └── (others unchanged)
├── tests/
│   ├── test_chunk_topo.py            # NEW
│   ├── test_vault_filter.py          # NEW
│   └── (others unchanged)
├── README.md                         # MODIFIED: v0.5 section
├── CHANGELOG.md                      # MODIFIED: [0.5.0] entry
└── docs/roadmap.md                   # MODIFIED: v0.5 shipped, v0.6 redefined
```

**Expected test count:** 94 (v0.4) → ~104.

---

## Task 1: Branch setup

- [ ] **Step 1.1: Verify main baseline**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git checkout main
. .venv/bin/activate
pytest -q && ruff check .
```
Expected: 94 passed, ruff clean.

- [ ] **Step 1.2: Create feat/v0.5**

```bash
git checkout -b feat/v0.5
```

- [ ] **Step 1.3: No commit — housekeeping only**

---

## Task 2: `scripts/chunk_topo.py` — topological wave planner

**Files:**
- Create: `scripts/chunk_topo.py`
- Create: `tests/test_chunk_topo.py`

- [ ] **Step 2.1: Write failing tests — `tests/test_chunk_topo.py`**

```python
"""Tests for scripts/chunk_topo.py — topological wave planner for parallel chunk dispatch."""
import pytest

from scripts.chunk_topo import CycleError, DependencyError, plan_waves


def test_empty_input():
    assert plan_waves([]) == []


def test_single_chunk_no_deps():
    chunks = [{"id": "scaffold"}]
    assert plan_waves(chunks) == [["scaffold"]]


def test_linear_chain_produces_n_waves_of_one():
    chunks = [
        {"id": "a"},
        {"id": "b", "depends_on": ["a"]},
        {"id": "c", "depends_on": ["b"]},
    ]
    waves = plan_waves(chunks)
    assert waves == [["a"], ["b"], ["c"]]


def test_independent_pair_in_same_wave():
    chunks = [
        {"id": "scaffold"},
        {"id": "parser", "depends_on": ["scaffold"]},
        {"id": "counters", "depends_on": ["scaffold"]},
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert set(waves[1]) == {"parser", "counters"}
    assert len(waves) == 2


def test_mdstats_shape_produces_five_waves():
    """mdstats: scaffold → [parser, counters] → aggregator → report → cli.
    Expected: 5 waves from 6 chunks."""
    chunks = [
        {"id": "scaffold"},
        {"id": "parser", "depends_on": ["scaffold"]},
        {"id": "counters", "depends_on": ["scaffold"]},
        {"id": "aggregator", "depends_on": ["counters"]},
        {"id": "report", "depends_on": ["aggregator"]},
        {"id": "cli", "depends_on": ["parser", "report"]},
    ]
    waves = plan_waves(chunks)
    assert len(waves) == 5
    assert waves[0] == ["scaffold"]
    assert set(waves[1]) == {"parser", "counters"}
    assert waves[2] == ["aggregator"]
    assert waves[3] == ["report"]
    assert waves[4] == ["cli"]


def test_missing_dependency_raises():
    chunks = [
        {"id": "a", "depends_on": ["does_not_exist"]},
    ]
    with pytest.raises(DependencyError, match="does_not_exist"):
        plan_waves(chunks)


def test_cycle_raises():
    chunks = [
        {"id": "a", "depends_on": ["b"]},
        {"id": "b", "depends_on": ["a"]},
    ]
    with pytest.raises(CycleError, match="cycle"):
        plan_waves(chunks)


def test_duplicate_chunk_ids_raises():
    chunks = [{"id": "a"}, {"id": "a"}]
    with pytest.raises(DependencyError, match="duplicate"):
        plan_waves(chunks)


def test_chunks_preserves_yaml_order_within_wave():
    """When two chunks are in the same wave, the output should be deterministic
    (sorted by id for stability)."""
    chunks = [
        {"id": "scaffold"},
        {"id": "zz", "depends_on": ["scaffold"]},
        {"id": "aa", "depends_on": ["scaffold"]},
    ]
    waves = plan_waves(chunks)
    assert waves[1] == ["aa", "zz"]  # sorted
```

- [ ] **Step 2.2: Run — confirm failure**

```bash
pytest tests/test_chunk_topo.py -v
```
Expected: all FAIL — module not found.

- [ ] **Step 2.3: Implement `scripts/chunk_topo.py`**

```python
#!/usr/bin/env python3
"""Topological wave planner for chunk dispatch.

Reads a chunks list (same shape as chunks.yaml's `chunks[]`) and groups
chunks into execution "waves": each wave is a set of chunks that can
dispatch concurrently because none of them depend on another in the
same wave.

Contract:
    plan_waves(chunks: list[dict]) -> list[list[str]]

Raises:
    DependencyError — duplicate chunk ids, or depends_on references
                      a chunk that doesn't exist.
    CycleError     — the depends_on graph contains a cycle.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class DependencyError(ValueError):
    """Raised for duplicate chunk ids or unresolvable depends_on references."""


class CycleError(ValueError):
    """Raised when the depends_on graph contains a cycle."""


def plan_waves(chunks: list[dict]) -> list[list[str]]:
    """Group chunks into execution waves by topological sort of depends_on.

    Each wave is returned as a sorted list of chunk ids for determinism.
    """
    if not chunks:
        return []

    ids = [c["id"] for c in chunks]
    if len(ids) != len(set(ids)):
        seen: set[str] = set()
        dupes = [i for i in ids if i in seen or seen.add(i)]  # type: ignore[func-returns-value]
        raise DependencyError(f"duplicate chunk ids: {sorted(set(dupes))}")

    id_set = set(ids)
    deps = {c["id"]: list(c.get("depends_on") or []) for c in chunks}

    # Validate that every depends_on references a real chunk
    for chunk_id, chunk_deps in deps.items():
        for dep in chunk_deps:
            if dep not in id_set:
                raise DependencyError(
                    f"chunk '{chunk_id}' depends_on '{dep}' which is not a known chunk"
                )

    waves: list[list[str]] = []
    remaining = set(ids)
    satisfied: set[str] = set()

    while remaining:
        # A chunk can run now iff all its deps are satisfied
        wave = sorted(cid for cid in remaining if all(d in satisfied for d in deps[cid]))
        if not wave:
            unresolved = sorted(remaining)
            raise CycleError(f"cycle detected among chunks: {unresolved}")
        waves.append(wave)
        satisfied.update(wave)
        remaining.difference_update(wave)

    return waves


def _load_chunks_yaml(path: Path) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text()) or {}
    chunks = data.get("chunks") or []
    if not isinstance(chunks, list):
        raise DependencyError("chunks.yaml must contain a `chunks:` list")
    return chunks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid chunks.yaml wave planner")
    ap.add_argument("--chunks-file", required=True, type=Path)
    args = ap.parse_args(argv)
    chunks = _load_chunks_yaml(args.chunks_file)
    waves = plan_waves(chunks)
    sys.stdout.write(json.dumps({"waves": waves}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2.4: Run tests**

```bash
pytest tests/test_chunk_topo.py -v
```
Expected: 9 pass.

- [ ] **Step 2.5: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 94 + 9 = 103 total, ruff clean.

- [ ] **Step 2.6: Commit**

```bash
git add scripts/chunk_topo.py tests/test_chunk_topo.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(topo): chunk wave planner for parallel dispatch

scripts/chunk_topo.plan_waves(chunks) groups chunks into execution
waves by topological sort of depends_on. Each wave is a set of chunks
that can dispatch concurrently. Raises DependencyError on unknown
depends_on refs or duplicate ids; CycleError on cycles.

Foundation for v0.5's parallel chunks feature — build skill reads
waves and dispatches each wave's chunks concurrently via Agent()."
```

---

## Task 3: `build` skill — wave dispatch prose

**Files:**
- Modify: `skills/build/SKILL.md`

- [ ] **Step 3.1: Read current file**

Read `skills/build/SKILL.md`. Locate the "Per-chunk dispatch loop" section (step 3 of the fresh-start flow). Currently it says "For each chunk in `chunks.yaml` in order".

- [ ] **Step 3.2: Update the dispatch section**

Replace the current step 3 intro (the line that starts "For each chunk in `chunks.yaml` in order:") with:

```markdown
3. **Wave-based dispatch loop.** First, compute execution waves:

   ```bash
   python <plugin-root>/scripts/chunk_topo.py --chunks-file .skillgoid/chunks.yaml
   ```

   The output is a JSON object `{"waves": [["a"], ["b", "c"], ["d"]]}` where each wave is a set of chunks that can dispatch concurrently (all dependencies satisfied). For purely sequential projects, every wave has one chunk — identical to v0.4 behavior.

   For each wave in order:

   3a. For each chunk in the wave (in parallel, via concurrent `Agent()` calls), check dependencies (safety re-check): every listed `chunk.depends_on` must have exited successfully in a prior wave.

   3b. Build the subagent prompt with the curated context slice (same template as v0.4 — chunk spec, retrieve_summary, blueprint, prior iterations if resuming).

   3c. Dispatch each chunk's subagent concurrently:
      ```
      Agent(
        subagent_type="general-purpose",
        model=<criteria.models.chunk_subagent or "sonnet">,
        description="Execute Skillgoid chunk <chunk_id>",
        prompt=<curated prompt>,
      )
      ```
      When multiple chunks are in the same wave, these dispatches run in parallel. Claude Code's `Agent` tool supports concurrent subagent invocation from a single message containing multiple `Agent` tool calls.

   3d. **Wait for every subagent in the wave to return** before evaluating results. This guarantees within-wave isolation.

   3e. Parse each subagent's JSON response and accumulate into orchestration state.

   3f. **Wave gate check**, evaluated after ALL subagents in the wave report:
      - If every chunk in the wave exited `success`: proceed to the next wave.
      - If any chunk exited `budget_exhausted` or `stalled`: STOP. Do NOT dispatch subsequent waves. Surface ALL failures (possibly multiple siblings) to the user with the three-option recovery menu (resume / unstick / retrospect-only). Note: `/skillgoid:unstick` is capped at 3 invocations per chunk.

   After all waves complete successfully, proceed to step 4 (integration phase).
```

Use Edit with enough surrounding context to uniquely identify the insertion point.

- [ ] **Step 3.3: Verify frontmatter**

```bash
python -c "import yaml; f=open('skills/build/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1])['name'])"
```
Expected: `build`.

- [ ] **Step 3.4: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 103 total (no code changes), ruff clean.

- [ ] **Step 3.5: Commit**

```bash
git add skills/build/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(build): wave-based parallel chunk dispatch

build skill now computes execution waves via scripts/chunk_topo.py,
then dispatches every chunk in a wave concurrently via parallel
Agent() calls. Waits for all subagents in a wave to return before
evaluating results.

Sequential chunks (all v0.4 projects) still work — each wave has one
chunk. Independent chunks (mdstats's parser + counters) now
parallelize for real wall-clock savings.

Exit behavior unchanged: first wave with any stall/budget-exhausted
chunk stops the project; all failures surfaced together."
```

---

## Task 4: `feasibility` skill — scaffolding awareness

**Files:**
- Modify: `skills/feasibility/SKILL.md`

- [ ] **Step 4.1: Read current file**

Find procedure step 3 (the "For each gate with env:" section that checks PYTHONPATH-style values).

- [ ] **Step 4.2: Replace step 3 with scaffolding-aware version**

Replace:

```markdown
3. **For each gate with `env:`** — check PATH-like values (`PYTHONPATH`, `PATH`): relative paths must resolve under the project dir (`src/` exists if `PYTHONPATH: src` is declared).
```

With:

```markdown
3. **For each gate with `env:`** — check PATH-like values (`PYTHONPATH`, `PATH`):
   - If the path value is **absolute**: must exist. Failure is hard.
   - If the path value is **relative** (e.g., `src`): resolve against project dir.
     - If it exists: ok.
     - If it doesn't exist AND the path is within the project dir: downgrade to a warning with hint `"relative path '<path>' doesn't exist yet — if your scaffold chunk creates it, this is expected on a fresh project; otherwise fix the config"`. Warnings don't block feasibility on this check alone.
     - If it doesn't exist AND the path is outside the project dir: hard failure.
   - Rationale: on fresh projects, scaffold chunk creates `src/` etc. Failing feasibility on paths the build loop will create is a false positive — observed in v0.4 on both taskq and mdstats real runs.
```

Use Edit with appropriate context.

- [ ] **Step 4.3: Verify frontmatter + spot-check**

```bash
python -c "import yaml; f=open('skills/feasibility/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1])['name'])"
grep -n 'scaffold chunk creates\|downgrade to a warning' skills/feasibility/SKILL.md
```

- [ ] **Step 4.4: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 103 total, ruff clean.

- [ ] **Step 4.5: Commit**

```bash
git add skills/feasibility/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(feasibility): scaffolding awareness — downgrade missing-path to warning

When a gate env: PYTHONPATH references a relative path inside the
project dir that doesn't exist yet, feasibility now emits a WARNING
(not a failure) with the hint that scaffold chunk may create it.

Observed in 2/3 real runs (taskq, mdstats): feasibility pre-plan
falsely failed on PYTHONPATH: src because src/ hadn't been scaffolded
yet. Hard-fails only kept for absolute paths or paths outside project."
```

---

## Task 5: `vault_filter.py` helper + tests

**Files:**
- Create: `scripts/vault_filter.py`
- Create: `tests/test_vault_filter.py`

- [ ] **Step 5.1: Write failing tests — `tests/test_vault_filter.py`**

```python
"""Tests for scripts/vault_filter.py — filter vault lessons by Status: resolved in vX.Y."""
import pytest

from scripts.vault_filter import (
    filter_lessons,
    parse_lessons,
    parse_version,
)


SAMPLE = """# python lessons

<!-- curated by Skillgoid retrospect — edit with care -->

## Lesson A

Current advice.

Last touched: 2026-04-17 by project "jyctl"

## Lesson B (resolved)

Old advice superseded.

Status: resolved in v0.4
Last touched: 2026-04-18 by project "taskq"

## Lesson C

More current advice.

Last touched: 2026-04-18 by project "mdstats"
"""


class TestParseVersion:
    def test_plain_version(self):
        assert parse_version("0.4") == (0, 4)

    def test_with_v_prefix(self):
        assert parse_version("v0.4") == (0, 4)

    def test_three_segments(self):
        assert parse_version("0.4.2") == (0, 4, 2)

    def test_invalid_returns_none(self):
        assert parse_version("not a version") is None


class TestParseLessons:
    def test_split_by_h2_headings(self):
        lessons = parse_lessons(SAMPLE)
        assert len(lessons) == 3
        assert lessons[0]["title"] == "Lesson A"
        assert lessons[1]["title"] == "Lesson B (resolved)"
        assert lessons[2]["title"] == "Lesson C"

    def test_extracts_status_line(self):
        lessons = parse_lessons(SAMPLE)
        assert lessons[1]["resolved_in"] == (0, 4)
        assert lessons[0]["resolved_in"] is None
        assert lessons[2]["resolved_in"] is None

    def test_preamble_is_separate(self):
        """The H1 title + HTML comment before the first H2 is preserved as preamble."""
        lessons = parse_lessons(SAMPLE)
        # The preamble is not itself a lesson
        titles = [line["title"] for line in lessons]
        assert "python lessons" not in titles


class TestFilterLessons:
    def test_newer_plugin_suppresses_resolved(self):
        lessons = parse_lessons(SAMPLE)
        active, resolved = filter_lessons(lessons, current_version=(0, 4))
        assert [line["title"] for line in active] == ["Lesson A", "Lesson C"]
        assert [line["title"] for line in resolved] == ["Lesson B (resolved)"]

    def test_equal_version_suppresses_resolved(self):
        """If lesson is 'resolved in v0.4' and we're running v0.4, hide it."""
        lessons = parse_lessons(SAMPLE)
        active, resolved = filter_lessons(lessons, current_version=(0, 4))
        assert any(line["title"] == "Lesson B (resolved)" for line in resolved)

    def test_older_plugin_keeps_resolved_active(self):
        """Running v0.3 plugin against a lesson marked 'resolved in v0.4':
        the resolution isn't here yet, so the lesson still applies."""
        lessons = parse_lessons(SAMPLE)
        active, resolved = filter_lessons(lessons, current_version=(0, 3))
        active_titles = {line["title"] for line in active}
        assert "Lesson B (resolved)" in active_titles
        assert resolved == []

    def test_none_version_keeps_everything_active(self):
        """If plugin version can't be read, fail-open: don't filter."""
        lessons = parse_lessons(SAMPLE)
        active, resolved = filter_lessons(lessons, current_version=None)
        assert len(active) == 3
        assert resolved == []

    def test_malformed_status_line_treated_as_unresolved(self):
        text = "## Broken\n\nadvice\n\nStatus: not a real format\n"
        lessons = parse_lessons(text)
        assert lessons[0]["resolved_in"] is None
```

- [ ] **Step 5.2: Run — confirm failure**

```bash
pytest tests/test_vault_filter.py -v
```
Expected: FAIL — module missing.

- [ ] **Step 5.3: Implement `scripts/vault_filter.py`**

```python
#!/usr/bin/env python3
"""Vault lesson filter.

Parses a `<language>-lessons.md` file into lessons, reads each lesson's
optional `Status: resolved in vX.Y` line, and filters them by the
current Skillgoid plugin version.

Contract:
    parse_version(text: str) -> tuple[int, ...] | None
    parse_lessons(md: str) -> list[dict]
    filter_lessons(lessons, current_version) -> tuple[list, list]
        returns (active_lessons, resolved_lessons)

CLI:
    python scripts/vault_filter.py \\
        --lessons-file ~/.claude/skillgoid/vault/python-lessons.md \\
        --plugin-json .claude-plugin/plugin.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
_STATUS_RE = re.compile(r"(?mi)^Status:\s*resolved\s+in\s+(\S+)")


def parse_version(text: str) -> tuple[int, ...] | None:
    """Parse '0.4' or 'v0.4' or '0.4.2' into a tuple of ints, else None."""
    if not text:
        return None
    m = _VERSION_RE.match(text.strip())
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def parse_lessons(md: str) -> list[dict]:
    """Split a vault markdown file into lesson dicts.

    Each lesson dict has: title (str), body (str), resolved_in (tuple | None).
    The H1 title + any preamble before the first H2 is not a lesson.
    """
    lessons: list[dict] = []
    # Split on H2 headings (lines starting with "## ")
    sections = re.split(r"(?m)^##\s+(.+)$", md)
    # sections[0] is preamble (before first ## ); then pairs of (title, body)
    i = 1
    while i < len(sections):
        title = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        status_match = _STATUS_RE.search(body)
        resolved_in = parse_version(status_match.group(1)) if status_match else None
        lessons.append({"title": title, "body": body, "resolved_in": resolved_in})
        i += 2
    return lessons


def filter_lessons(
    lessons: list[dict],
    current_version: tuple[int, ...] | None,
) -> tuple[list[dict], list[dict]]:
    """Split lessons into (active, resolved) based on current_version.

    A lesson is 'resolved' if it has a `resolved_in` tuple AND
    current_version is not None AND current_version >= resolved_in.
    If current_version is None, fail-open and treat everything as active.
    """
    if current_version is None:
        return lessons, []
    active: list[dict] = []
    resolved: list[dict] = []
    for lesson in lessons:
        rv = lesson.get("resolved_in")
        if rv is not None and current_version >= rv:
            resolved.append(lesson)
        else:
            active.append(lesson)
    return active, resolved


def _read_plugin_version(plugin_json: Path) -> tuple[int, ...] | None:
    try:
        data = json.loads(plugin_json.read_text())
    except Exception:
        return None
    return parse_version(data.get("version") or "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid vault lesson filter")
    ap.add_argument("--lessons-file", required=True, type=Path)
    ap.add_argument("--plugin-json", required=True, type=Path)
    args = ap.parse_args(argv)

    if not args.lessons_file.exists():
        sys.stdout.write(json.dumps({"active": [], "resolved": []}) + "\n")
        return 0

    md = args.lessons_file.read_text()
    lessons = parse_lessons(md)
    version = _read_plugin_version(args.plugin_json)
    active, resolved = filter_lessons(lessons, version)
    sys.stdout.write(json.dumps({
        "active": [line["title"] for line in active],
        "resolved": [line["title"] for line in resolved],
    }) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5.4: Run tests**

```bash
pytest tests/test_vault_filter.py -v
```
Expected: ~11 pass.

- [ ] **Step 5.5: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 114 total (103 + 11), ruff clean.

- [ ] **Step 5.6: Commit**

```bash
git add scripts/vault_filter.py tests/test_vault_filter.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(vault): filter lessons by 'Status: resolved in vX.Y' line

scripts/vault_filter.py parses vault markdown files into lessons,
reads each lesson's optional Status: line, and filters by the current
Skillgoid plugin version. Returns (active, resolved) tuples so
retrieve can render resolved lessons in a collapsed section or hide
them entirely.

Fail-open: if plugin version can't be read, all lessons stay active.
Consumed by the retrieve skill."
```

---

## Task 6: `retrieve` skill — vault-filter prose update

**Files:**
- Modify: `skills/retrieve/SKILL.md`

- [ ] **Step 6.1: Update procedure step 2**

In `skills/retrieve/SKILL.md`, find procedure step 2 (reads `<language>-lessons.md`). Replace or extend it with:

```markdown
2. **Read** `~/.claude/skillgoid/vault/<language>-lessons.md` if it exists. Before surfacing lessons, filter by the current Skillgoid plugin version:

   ```bash
   python <plugin-root>/scripts/vault_filter.py \
       --lessons-file ~/.claude/skillgoid/vault/<language>-lessons.md \
       --plugin-json <plugin-root>/.claude-plugin/plugin.json
   ```

   The helper emits JSON: `{"active": [...], "resolved": [...]}`. Surface the **active** lessons as current advice; mention resolved lessons only if the user explicitly asks for history ("what lessons have been superseded?") or invoke `/skillgoid:retrieve --show-resolved`. Each active lesson's `Status:` line (if any) hints at which release resolved a PAST issue — carry through intact.

   If `vault_filter.py` can't determine the plugin version (malformed `plugin.json` or file missing), treat all lessons as active — fail-open to avoid hiding lessons the user might need.
```

- [ ] **Step 6.2: Verify frontmatter + spot-check**

```bash
python -c "import yaml; f=open('skills/retrieve/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1])['name'])"
grep -n 'vault_filter.py\|Status:' skills/retrieve/SKILL.md
```

- [ ] **Step 6.3: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 114 total, ruff clean.

- [ ] **Step 6.4: Commit**

```bash
git add skills/retrieve/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(retrieve): filter vault lessons by current plugin version

retrieve skill now invokes scripts/vault_filter.py to split vault
lessons into (active, resolved) sets based on the current plugin
version read from .claude-plugin/plugin.json. Only active lessons are
surfaced as current advice by default; resolved lessons are available
on demand.

Fail-open: if plugin version can't be read, no filtering happens."
```

---

## Task 7: Docs — README + CHANGELOG + roadmap

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/roadmap.md`

- [ ] **Step 7.1: `README.md` — insert "What's new in v0.5" BEFORE v0.4 section**

```markdown
## What's new in v0.5

Evidence-driven polish based on three real Skillgoid runs (jyctl, taskq, mdstats):

- **Parallel chunks.** `build` now groups chunks into waves via topological sort of `depends_on`, and dispatches every chunk in a wave concurrently. Sequential projects behave identically to v0.4; projects with independent chunks (like mdstats's parser + counters) run faster.
- **Vault supersession tracking.** Lessons in `<language>-lessons.md` can now carry a `Status: resolved in vX.Y` line. The `retrieve` skill filters them against the current plugin version so users don't get stale advice for bugs newer Skillgoid already fixed.
- **Feasibility scaffolding awareness.** `/skillgoid:feasibility` no longer hard-fails when `PYTHONPATH: src` references a path that doesn't exist yet (because the scaffold chunk will create it). Soft warning on fresh projects; hard failure only for absolute paths or paths outside the project.

No plan-refinement-mid-build — 3 real runs produced zero evidence that's needed. Re-evaluate after a run actually demonstrates the need.

All changes fully backward-compatible with v0.4.

```

- [ ] **Step 7.2: `CHANGELOG.md` — `[0.5.0]` entry**

```markdown
## [0.5.0] — 2026-04-18

### Added
- `scripts/chunk_topo.py` — topological wave planner for parallel chunk dispatch.
- `scripts/vault_filter.py` — filter vault lessons by `Status: resolved in vX.Y`.

### Changed
- `build` skill now dispatches chunks in waves (parallel within each wave). Sequential projects unchanged; projects with independent chunks run concurrently.
- `feasibility` skill downgrades missing-relative-path-inside-project to a warning.
- `retrieve` skill filters vault lessons against the current plugin version before surfacing.
- Vault lesson format gains an optional `Status: resolved in vX.Y` line.

### Backward compatibility
- v0.4 `criteria.yaml` / `chunks.yaml` / vault files parse unchanged.
- Sequential chunks behave identically to v0.4 (single-chunk waves).
- Vault files without `Status:` lines surface as current advice (same as v0.4).

### Notably NOT included
- Plan refinement mid-build (3 real runs produced 0 evidence it's needed).
- Rehearsal mode (overlaps with v0.4 feasibility).
- Polyglot / more language adapters / gate-type plugins / dashboards (no demand signal).

```

- [ ] **Step 7.3: `docs/roadmap.md` — mark v0.5 Shipped, redefine v0.6**

Replace the "## Deferred — v0.5 goals" section entirely with:

```markdown
### v0.5 — Evidence-Driven Polish (2026-04-18)
Small ship based on 3-real-run evidence:
- Parallel chunks (wave-based dispatch) — observed on mdstats (parser + counters independent)
- Vault supersession tracking — addresses stale lessons from jyctl era
- Feasibility scaffolding awareness — fixes false positive on fresh projects
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.5-evidence-driven-polish.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.5.md`

## Deferred — v0.6 goals

**Re-ranked by observed ROI.** Items that had zero evidence across 3 real runs are demoted; items that surfaced from actual failures are promoted.

### Demoted (kept deferred — no evidence after 3 real runs)

- **Plan refinement mid-build.** 0/3 runs demonstrated the need. Originally the highest-predicted-ROI item but consistently unvalidated. Don't ship on speculation. Revisit ONLY when a real run has a chunk whose iterations reveal downstream decomposition is wrong.
- **Rehearsal mode.** Subsumed by v0.4's feasibility + v0.5's scaffolding awareness.
- **Polyglot / multi-language.** No demand across 3 python projects.
- **Dashboards / HTML.** `/skillgoid:stats` markdown remains sufficient.
- **Tighter vault retrieval.** Vault has 5 entries — not a scale problem yet.
- **More language adapters.** No demand.
- **Gate-type plugins.** Premature abstraction.

### Possible v0.6 — when evidence demands

1. **Run Skillgoid on a STRUCTURALLY DIFFERENT project** (not another python CLI). Candidates: a small web service, a library with strict typing, a background worker with async I/O. Need shapes that stress different axes.
2. **Bigger vault query** — if `/skillgoid:stats` shows recurring stall signatures, a v0.6 feature could pre-emptively surface the matching vault lesson mid-build.
3. **Unstick actually invoked** — if a real run stalls and the user uses `/skillgoid:unstick`, evaluate whether its UX is good or needs v0.6 tweaks.

## How to pick up v0.6

1. Run `/skillgoid:stats` after v0.5 has been used on 3+ more real projects.
2. Look for recurring failure signatures — those are the real v0.6 priorities.
3. Don't revive v0.5's demoted items without new evidence.
```

- [ ] **Step 7.4: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 114 total, ruff clean.

- [ ] **Step 7.5: Commit**

```bash
git add README.md CHANGELOG.md docs/roadmap.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "docs: v0.5 release notes + roadmap refresh

README gains 'What's new in v0.5' summary. CHANGELOG adds [0.5.0]
entry. Roadmap moves v0.5 to Shipped, DEMOTES plan-refinement-
mid-build and other originally-high-predicted items that produced
zero evidence across 3 real runs, and defines v0.6 as 'wait for
more evidence from structurally different projects.'"
```

---

## Self-review

**Spec coverage:**
- §3.1 Vault supersession → Tasks 5 + 6.
- §3.2 Feasibility scaffolding awareness → Task 4.
- §3.3 Parallel chunks → Tasks 2 + 3.
- §4.1 Vault Status line format → Tasks 5 + 6.
- §5 Skill changes (build, feasibility, retrieve) → Tasks 3, 4, 6.
- §7 Tests → Tasks 2 + 5.

**Placeholder scan:** no TBD / TODO / "implement later." Skill prose uses `<plugin-root>` placeholder consistently with v0.2–v0.4 convention.

**Type/name consistency:**
- `plan_waves(chunks: list[dict]) -> list[list[str]]`, `CycleError`, `DependencyError` — Task 2 creates, no other task consumes by import (build skill invokes via CLI).
- `parse_lessons`, `parse_version`, `filter_lessons` — Task 5 creates, Task 6 invokes via CLI.
- `chunk_topo.py` CLI — `--chunks-file` flag, Task 3 build-skill prose invokes with this flag.
- `vault_filter.py` CLI — `--lessons-file` + `--plugin-json` flags, Task 6 retrieve-skill prose invokes with those.

No gaps. No drift.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-skillgoid-v0.5.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
