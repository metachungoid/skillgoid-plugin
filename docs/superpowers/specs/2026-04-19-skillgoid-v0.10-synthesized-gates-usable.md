# Skillgoid v0.10 — Synthesized Gates That Actually Work

**Version:** 0.9.0 → 0.10.0

**Depends on:** v0.9.0 (Phase 1.5 `synthesize-gates` skill).

**Evidence:** [`docs/superpowers/plans/2026-04-19-phase1.5-build-dogfood-findings.md`](../plans/2026-04-19-phase1.5-build-dogfood-findings.md) — labeled the three findings "v0.13" in draft; renumbered to v0.10 here for version/label alignment.

## Problem

The v0.9.0 `synthesize-gates` skill produces well-grounded `criteria.yaml.proposed` drafts, but when those drafts are used in `/skillgoid:build`, three usability gaps surface:

- **F1 — Analogue-clone contamination.** `ground.py` clones analogues into `.skillgoid/synthesis/analogues/<slug>/` *inside the project tree*. The resulting criteria's `ruff check .` lints the analogue, hiding the project's real lint posture.
- **F2 — `type: coverage` contract mismatch.** The synthesis subagent writes literal `coverage` CLI args (`run`, `report --fail-under=100`); the adapter (`_gate_coverage` in `scripts/measure_python.py`) ignores `args` entirely and hard-codes pytest-cov with `min_percent=80`. User-intended thresholds are silently dropped.
- **F3 — Duplicate coverage gates.** Synthesis emits `coverage-run` + `coverage-report` as two gates when they express one semantic (run-and-threshold).

## Goal

A synthesized `criteria.yaml.proposed` is directly usable by `/skillgoid:build` with no hand-editing of the coverage gate, no false-positive lint passes from analogue contamination, and no semantically-duplicate gates.

## Non-goals

- Phase 2 oracle validation (actually running the criteria against a stub build to prove it passes).
- context7 grounding fallback.
- Curated-template cold-start synthesis.
- Other-language gate adapters (rust-gates, js-gates) — don't exist yet; they'll inherit the canonical-shape lesson when they're added.
- New `.skillgoid/` tool-exclusion defaults — unneeded once analogues move out of the project tree.

## Design

### 13a — F2: `type: coverage` canonicalization

**Decision:** `type: coverage` is a declarative gate, not a runbook step. It carries `min_percent: int` and nothing CLI-shaped. Literal `coverage` CLI usage goes to `type: run-command`.

**Schema (`schemas/criteria.schema.json`):** under the `oneOf` variant for `type: coverage`:

- `min_percent` — required, integer, 0–100.
- `args` — disallowed (schema rejects).
- Existing `target`, `compare_to_baseline`, `timeout`, `env` — unchanged.

**Grounding (`scripts/synthesize/ground.py`):** new observation type `coverage_threshold`, extracted from two sources:

1. **`pyproject.toml#[tool.coverage.report]`.** If `fail_under` is present, emit `{observed_type: "coverage_threshold", value: <int>, ref: "<repo>/pyproject.toml#tool.coverage.report"}`. Falls within the existing tomllib-based pyproject parser; extends `_TOOL_SECTIONS` to include `coverage.report`.
2. **CI script / workflow step containing `--fail-under=N`.** During existing command classification, detect the `--fail-under=N` token (literal regex), emit `{observed_type: "coverage_threshold", value: <N>, ref: <existing ref>}`. Works for both direct workflow commands and followed wrapper scripts.

If both sources exist with different values, emit both observations; the subagent picks (prompt instructs: prefer CI-script value since it's enforced).

**Subagent prompt (`skills/synthesize-gates/prompts/synthesize.md`):** new section:

> For `type: coverage` gates, the canonical shape is `{type: coverage, min_percent: <int>}` — no `args` field. If you observe a `coverage_threshold` observation, use its value for `min_percent` and cite the observation's `ref` in provenance. If no `coverage_threshold` exists, default to `min_percent: 80` and note `"no threshold found in analogue, defaulting to 80"` in rationale.
>
> If the analogue uses the `coverage` CLI in a non-standard way (e.g., `coverage combine`, `coverage erase`), emit a separate `type: run-command` gate for each distinct CLI invocation. Don't conflate literal CLI usage with threshold enforcement.

**Validator (`scripts/synthesize/synthesize.py` Stage 2):** new per-draft check:

- If `draft.type == "coverage"`:
  - Reject if `args` is present and non-empty: `"coverage gate '<id>' must not have args; use type: run-command for literal CLI usage"`.
  - Reject if `min_percent` is missing: `"coverage gate '<id>' must have min_percent (int, 0-100)"`.
  - Reject if `min_percent` is out of range: `"coverage gate '<id>' min_percent must be 0-100 (got <value>)"`.

Exit 1 on any rejection; Phase 1 no-retry policy applies.

### 13b — F1: analogue clones out of project tree

**Decision:** analogues live in the user-global cache dir, not the project.

**Location (`scripts/synthesize/ground.py`):**

```python
def _cache_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    try:
        base.mkdir(parents=True, exist_ok=True)
        (base / "skillgoid" / "analogues").mkdir(parents=True, exist_ok=True)
        return base / "skillgoid" / "analogues"
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "skillgoid-analogues"
        fallback.mkdir(parents=True, exist_ok=True)
        sys.stderr.write(f"warning: cache dir unwritable, using {fallback}\n")
        return fallback
```

Git URLs clone to `_cache_dir() / <slug>/`. Local path analogues are used as-is (no copy needed).

**Migration:** on next `ground.py` run, if `<project>/.skillgoid/synthesis/analogues/<slug>/` exists:

- If the cache-dir copy doesn't exist: move (rename) project-local → cache-dir. One-time migration.
- If both exist: leave both untouched; stderr warning `"analogue cache already exists at <cache-path>; project-local copy at <project-path> is now orphaned, please remove manually"`.
- Log each migration to stderr: `"migrated <slug> analogue to <cache-path>"`.

**`grounding.json` refs:** unchanged. Refs are opaque display strings (`encode-httpx/pyproject.toml#...`); the validator checks set-membership against grounding observations, not filesystem existence.

### 13c — F3: duplicate coverage-gate collapse

**Decision:** `synthesize.py` Stage 2 collapses multiple `type: coverage` drafts into one after per-gate validation passes.

**Rule:**

- After per-gate validation, if `len([d for d in drafts if d.type == "coverage"]) > 1`:
  - Keep one draft with `min_percent = max(d.min_percent for d in coverage_drafts)`.
  - Union `provenance.ref` into a list if multiple unique refs (update schema `provenance` to accept `ref: str | list[str]` — or wrap in a single `refs: list[str]` field; see Open question below).
  - Concatenate `rationale` with `" + "`.
  - Replace the old drafts in the output list.
- Log to stderr: `"collapsed <N> coverage drafts into one (min_percent=<max>)"`.

Under 13a's strict validator the subagent should emit at most one coverage draft anyway — this rule is belt-and-suspenders for prompt-compliance gaps.

### Data flow

```
[analogue repo] → ground.py → grounding.json
    clone → ~/.cache/skillgoid/analogues/<slug>/  (NEW: cache-dir not project)
    observations: ruff, mypy, pytest, ..., coverage_threshold (NEW)
    (migration: project-local → cache-dir on first run after upgrade)

grounding.json + goal.md → synthesis subagent (prompt teaches canonical shape)
                       → drafts JSON

drafts JSON → synthesize.py Stage 2:
    (a) per-draft validation (NEW: coverage shape check)
    (b) post-validation collapse (NEW: duplicate coverage merge)
           → validated drafts → write_criteria.py → criteria.yaml.proposed
```

### Error handling summary

| Failure | Behavior |
|---|---|
| Cache dir unwritable | Fallback `$TMPDIR/skillgoid-analogues/`; stderr warning |
| Migration conflict (both copies exist) | Leave both; stderr warning with explicit manual-remove instruction |
| `type: coverage` with args | Stage 2 exit 1 with `"coverage gate '<id>' must not have args; use type: run-command for literal CLI usage"` |
| `type: coverage` without min_percent | Stage 2 exit 1 with `"coverage gate '<id>' must have min_percent (int, 0-100)"` |
| `type: coverage` with min_percent out of range | Stage 2 exit 1 with explicit range message |
| Multiple coverage drafts | Collapsed silently with stderr notice |

## Components changed

| File | Kind | Change |
|---|---|---|
| `schemas/criteria.schema.json` | schema | Coverage `oneOf` variant — min_percent required, args forbidden |
| `scripts/synthesize/ground.py` | code | Cache-dir clone + migration; `coverage_threshold` observation |
| `scripts/synthesize/synthesize.py` | code | Coverage-shape validator; duplicate collapse |
| `skills/synthesize-gates/prompts/synthesize.md` | prompt | Canonical-shape teaching; run-command escape hatch |
| `skills/synthesize-gates/SKILL.md` | doc | Limitations block update |
| `tests/test_ground_analogue.py` | test | Cache-dir location, migration, threshold extraction |
| `tests/test_synthesize.py` | test | Invalid-shape rejection; duplicate collapse |
| `tests/test_synthesize_e2e.py` | test | Updated e2e assertions for canonical coverage gate |
| `tests/fixtures/synthesize/mini-flask-demo/` | fixture | Add `[tool.coverage.report].fail_under=100` + CI `--fail-under=95` |
| `.claude-plugin/plugin.json` | config | Version bump 0.9.0 → 0.10.0 |

## Testing

**New unit tests:**

- `coverage_threshold` extraction from `[tool.coverage.report].fail_under` (present / absent).
- `coverage_threshold` extraction from CI step containing `--fail-under=N` (direct step / via followed wrapper).
- Both sources present with different values → two observations emitted.
- Cache-dir clone target resolution with/without `XDG_CACHE_HOME`.
- Cache-dir unwritable fallback to `$TMPDIR`.
- Migration: project-local `.skillgoid/synthesis/analogues/<slug>/` moves to cache when cache is empty.
- Migration conflict: both exist → warning, both preserved.
- Validator rejects `type: coverage` with `args` (exits 1 with specific message).
- Validator rejects `type: coverage` without `min_percent`.
- Validator rejects `min_percent` out of range.
- Duplicate collapse: two coverage drafts → one, max min_percent wins.

**E2E update (`test_synthesize_e2e.py`):**

- Fixture `mini-flask-demo` gains `[tool.coverage.report].fail_under=100` and a CI step `coverage report --fail-under=95`.
- Grounding asserts both `coverage_threshold` observations present with values 100 and 95.
- Simulated subagent output emits one `type: coverage` gate with `min_percent: 100` (or 95 — either pick passes if prompt instruction is followed; test asserts the subagent's choice is provenance-cited).
- Final `criteria.yaml.proposed` asserts the coverage gate has no `args` and has `min_percent` set.

## Open question (resolve during implementation, not blocking spec)

The `provenance` field in drafts is currently `{source: str, ref: str}` (single ref). After 13c collapse of multiple coverage drafts, we need to preserve multiple refs. Three options:

1. **Widen `ref` to `str | list[str]`.** Schema and write_criteria.py both update.
2. **Add separate `refs: list[str]` alongside `ref`.** Keep single-ref case clean.
3. **Keep single `ref`; emit the collapsed draft's `ref` as a synthetic "merged:<ref1>+<ref2>" string.** No schema change; ugly provenance.

Implementation plan should pick one. Recommend **1** (widen) — cleanest, single code path.

## Risks

- **Subagent prompt drift.** Teaching the canonical shape is prose; the subagent may still emit CLI-shaped coverage drafts. Dedup + validator-reject serves as belt-and-suspenders but means some runs fail at Stage 2 until prompt is re-tuned.
- **Cross-platform cache-dir.** `~/.cache/` is XDG-standard on Linux; on macOS convention differs (`~/Library/Caches/`). Acceptable: we're Linux-focused; if macOS users surface, add platform branch later.
- **Migration fragility.** Moving directories is atomic on POSIX but the `.skillgoid/synthesis/analogues/` parent may be git-ignored or git-tracked; migration is idempotent and non-destructive (fallback on conflict), so this is low-risk.

## Backward compatibility

- Existing `criteria.yaml` files with `type: coverage` using the old loose shape (no `min_percent`, args present) **remain valid at the adapter level** — the adapter continues to ignore args and uses default `min_percent=80`. v0.10 tightens only the synthesis-stage validator, not the adapter's runtime acceptance. Users whose hand-authored `criteria.yaml` uses the old shape see no behavior change.
- **Synthesis re-runs** against analogues will produce the new shape. If a user regenerates and the new shape crashes their build script somewhere downstream, they can edit back.
- Existing `.skillgoid/synthesis/analogues/` directories in user projects are migrated on next ground run — non-destructive unless both copies exist.

## Implementation sequencing

Recommend the implementation plan batch tasks roughly:

1. **Schema + validator change** (13a-partial). Smallest foothold.
2. **Ground.py `coverage_threshold` observation** (13a). Extends existing tool-section parser.
3. **Subagent prompt update** (13a). Prose-only.
4. **Ground.py cache-dir + migration** (13b). Independent of 13a.
5. **Duplicate collapse** (13c). Depends on 13a validator for draft typing.
6. **E2E fixture + test update** (cross-cutting).
7. **SKILL.md update + version bump** (ship).

Tasks 1 and 4 can run in parallel; 5 depends on 1; 6 depends on 1–5.
