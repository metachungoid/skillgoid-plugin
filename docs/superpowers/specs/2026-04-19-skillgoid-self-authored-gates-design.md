# Skillgoid Self-Authored Gates from Observation — Design Spec

**Status:** Draft
**Date:** 2026-04-19
**Scope:** Multi-release arc (likely v0.13 + v0.14). Not a single version bump.

## Problem

`criteria.yaml` is the contract that defines "done" for every Skillgoid project. It is hand-authored by the user today. That hand-authoring is the single remaining human bottleneck in an otherwise mechanical pipeline — `clarify`, `decompose`, `build`, `integrate`, `retrospect` are all agent-driven; only the gate definition is not.

Hand-authoring requires the user to already think in test-shaped terms ("what commands, what thresholds, what exit codes define success?"). That gates the tool's audience to people who would already write their own test harness. The revolutionary move is to invert this: given a rough goal and one or more analogue reference points, the system observes what "done" looks like in working projects and proposes a contract. The user's job moves from authoring gates to *reviewing* them.

This spec defines a new skill, `/skillgoid:synthesize-gates`, that owns `criteria.yaml` authoring end-to-end.

## Goal

Produce `criteria.yaml` from observation of three grounding sources, with per-gate provenance and oracle validation, such that the user's acceptance step is editing a drafted YAML file (not authoring from scratch).

## Non-goals (v1)

- No chunk decomposition — `chunks.yaml` stays hand-authored (deferred to v0.14+).
- No auto-discovery of analogue repos via GitHub search — the user points to analogues, or the template fallback triggers.
- No hermetic sandboxing of oracle validation — runs in a tmpdir with the user's local toolchain.
- No iterative gate refinement loop — one-shot synthesis. Refinement happens via manual edit or `/skillgoid:unstick`-style intervention.
- No live-LLM test coverage — synthesis model dispatch is mocked at the test boundary.

## Architecture

Four-stage pipeline, each stage a script in `scripts/synthesize/` invoked in order by `skills/synthesize-gates/SKILL.md`. Per-stage JSON artifacts in `.skillgoid/synthesis/` support debuggability and recovery.

```
goal.md → [Ground] → [Synthesize] → [Validate] → [Write]
                ↓           ↓            ↓           ↓
          analogue repo  draft gates  oracle run  criteria.yaml
          context7 docs  with source  + scaffold  with provenance
          templates      attribution  run         comments
```

Outputs:
- `.skillgoid/synthesis/grounding.json` — observation corpus with source attribution.
- `.skillgoid/synthesis/drafts.json` — candidate gates (unvalidated).
- `.skillgoid/synthesis/validated.json` — candidate gates with validation labels.
- `criteria.yaml` — final user-facing contract with provenance comments.

### Stage 1: Ground

Three sources, queried in order. All three can contribute to the union corpus.

**1a. User-pointed analogues.** CLI signature:

```
/skillgoid:synthesize-gates <repo-url-or-path> [<repo2> ...]
```

If no args given, the skill interactively prompts for one or more analogues (or "skip"). Each analogue is cloned (if URL) or symlinked (if local path) into `.skillgoid/synthesis/analogues/<slug>/`, where `<slug>` is derived from the URL's owner+repo (`github.com/shlink/shlink` → `shlink-shlink`) or the local directory basename. The grounding stage reads:

- Test files (identified by glob patterns per language — `tests/**/*.py`, `**/*_test.go`, `**/*.test.ts`, etc.).
- CI configs (`.github/workflows/*.yml`, `.circleci/config.yml`, `.gitlab-ci.yml`).
- Package manifests (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`) for declared test commands and lint configs.
- Top-level lint/format configs (`.ruff.toml`, `.eslintrc*`, `.golangci.yml`).

Extracts observed gate patterns: `{command, cwd, context, source_file}` tuples.

**1b. Context7.** Given the language and primary framework detected from `goal.md` (and cross-referenced against any analogue repo's manifest), the skill queries the context7 MCP for current docs on that framework's testing patterns. Example queries: "Flask testing patterns", "pytest-asyncio best practices", "React Testing Library component assertions". Extracts: `{pattern_name, example_command, source_doc_id}` tuples. If context7 MCP is unavailable, skip this source and continue — do not fail.

**1c. Curated templates.** Ships under `plugin/templates/gate-library/<domain>.yaml`. Initial v1 set:

- `python-web-api.yaml` (Flask/FastAPI route tests, schema validation, error-handling gates)
- `python-cli.yaml` (argparse smoke, stdin/stdout contracts, exit-code gates)
- `python-data-pipeline.yaml` (fixture-based transformation tests, schema conformance)
- `node-web-api.yaml` (Express/Fastify route tests, JSON schema, auth gates)
- `go-cli.yaml` (cobra subcommand smoke, stdout golden-file tests)

Template selection: keyword match on `goal.md` (e.g., "CLI", "web API", "pipeline") + detected language. Highest-scoring template contributes its gates to the corpus; ties broken by alphabetical order of template ID (deterministic). If no template scores above threshold, no template contribution.

**Output of Stage 1:** `.skillgoid/synthesis/grounding.json`:

```json
{
  "language_detected": "python",
  "framework_detected": "flask",
  "observations": [
    {"source": "analogue", "ref": "shlink/tests/test_redirect.py:42", "command": "pytest tests/test_redirect.py", "context": "route test"},
    {"source": "context7", "ref": "flask-docs/testing-pattern-1", "command": "pytest tests/test_app_factory.py::test_create_app", "context": "app factory smoke"},
    {"source": "template", "ref": "python-web-api:route-schema-gate", "command": "pytest tests/test_schema.py", "context": "schema validation"}
  ]
}
```

### Stage 2: Synthesize

**Precondition:** `grounding.json` must contain at least one observation. If all three sources produced zero observations (no analogue provided, context7 unavailable, no template matched), Stage 2 fails fast with:

```
synthesize-gates: no grounding sources produced observations.
Provide an analogue repo:
  /skillgoid:synthesize-gates <repo-url>
Or hand-author .skillgoid/criteria.yaml directly.
```

Dispatched subagent consumes `grounding.json` + `goal.md` and drafts gate specs. Prompt template: `skills/synthesize-gates/prompts/synthesize.md`. Subagent output (parsed into `.skillgoid/synthesis/drafts.json`):

```json
{
  "drafts": [
    {
      "id": "pytest_redirect",
      "command": "pytest tests/test_redirect.py",
      "cwd": ".",
      "timeout_sec": 60,
      "provenance": {"source": "analogue", "ref": "shlink/tests/test_redirect.py:42"},
      "rationale": "Analogue repo has canonical redirect test; goal.md mentions URL redirection as core behavior."
    }
  ]
}
```

Synthesis constraint: every draft gate MUST cite a `provenance` entry traceable back to `grounding.json`. Gates without provenance are rejected at parse time (prevents LLM hallucination of commands that weren't observed).

### Stage 3: Validate — oracle with graceful degradation

For each draft gate, execute twice in a tmpdir:

**Should-pass run.**
- For `source: analogue` gates: run against the checked-out analogue repo as `cwd`. Expected: exit 0.
- For `source: context7` or `source: template` gates: run against a minimal fixture repo bundled in the plugin (`plugin/templates/fixture-repos/<language>/`). Expected: exit 0.

**Should-fail run.**
- Run against an empty scaffold directory (tmpdir with just the gate's expected file stubs as empty files). Expected: non-zero exit.

**Classification per gate:**

| should-pass | should-fail | label                        | warn                                      |
|-------------|-------------|------------------------------|-------------------------------------------|
| exit 0      | exit ≠ 0    | `validated: oracle`          | —                                         |
| exit 0      | exit 0      | `validated: smoke-only`      | `does not discriminate`                   |
| exit ≠ 0    | —           | `validated: none`            | `should-pass failed: <stderr excerpt>`    |
| timeout     | —           | `validated: none`            | `timeout after N sec`                     |
| install err | —           | `validated: none`            | `analogue install failed: <stderr>`       |

Gates with `validated: none` remain in the draft so the user can edit them; the warn label makes the issue visible in the rendered `criteria.yaml`.

**Output:** `.skillgoid/synthesis/validated.json` — drafts plus validation label + warn text per gate.

**Operational guardrails:**
- Per-gate timeout: 90 seconds default, overridable per template.
- Total validation stage timeout: 10 minutes. If exceeded, remaining gates are labeled `validated: none, warn: validation stage timed out`.
- Validation stage is skippable via `--skip-validation` flag (gates go straight to Write with `validated: none` label). Escape hatch for offline work or broken analogues; not recommended for normal use.

### Stage 4: Write

Renders `criteria.yaml` with comment headers per gate:

```yaml
# Skillgoid criteria — synthesized 2026-04-19 from:
#   analogue: shlink/shlink
#   context7: flask-docs
#   template: python-web-api
# Review each gate below. Delete ones you don't want. Edit commands as needed.

gates:
  # source: analogue, ref: shlink/tests/test_redirect.py:42
  # validated: oracle (discriminates empty scaffold)
  - id: pytest_redirect
    command: pytest tests/test_redirect.py
    cwd: .
    timeout_sec: 60

  # source: context7, ref: flask-docs/testing-pattern-1
  # validated: smoke-only, warn: empty scaffold also passes — consider tightening
  - id: flask_app_factory_smoke
    command: pytest tests/test_app_factory.py::test_create_app
    cwd: .
    timeout_sec: 30

  # source: template, ref: python-web-api:route-schema-gate
  # validated: none, warn: analogue install failed (missing postgres)
  - id: pytest_route_schema
    command: pytest tests/test_schema.py
    cwd: .
    timeout_sec: 60
```

If `criteria.yaml` already exists, write to `criteria.yaml.proposed` instead and print a notice directing the user to diff and merge manually. Never overwrite an existing `criteria.yaml`.

## Change to `clarify`

`clarify` stops producing `criteria.yaml`. It produces `goal.md` only. Its final print message changes to:

```
goal.md written to .skillgoid/goal.md

Next step: synthesize a gate contract.
  /skillgoid:synthesize-gates <analogue-repo-url>

If you have an analogue project in mind ("build me a URL shortener
like shlink/shlink"), pass its URL or local path. Otherwise run
without args and the skill will walk you through options.
```

Existing projects with hand-authored `criteria.yaml` continue to work unchanged — `build` doesn't care who wrote `criteria.yaml`. The skill itself is additive; only `clarify`'s output changes.

## File structure

```
plugin/
├── skills/
│   └── synthesize-gates/
│       ├── SKILL.md
│       └── prompts/
│           └── synthesize.md
├── scripts/
│   └── synthesize/
│       ├── ground_analogue.py         # Stage 1a
│       ├── ground_context7.py         # Stage 1b
│       ├── ground_template.py         # Stage 1c
│       ├── ground.py                  # Stage 1 orchestrator (calls 1a/1b/1c, writes grounding.json)
│       ├── synthesize.py              # Stage 2 (dispatches subagent, parses output, writes drafts.json)
│       ├── validate.py                # Stage 3 (oracle runs, writes validated.json)
│       └── write_criteria.py          # Stage 4 (renders criteria.yaml with provenance comments)
├── templates/
│   ├── gate-library/
│   │   ├── python-web-api.yaml
│   │   ├── python-cli.yaml
│   │   ├── python-data-pipeline.yaml
│   │   ├── node-web-api.yaml
│   │   └── go-cli.yaml
│   └── fixture-repos/
│       ├── python/                    # minimal Flask fixture for template/context7 validation
│       ├── node/
│       └── go/
└── tests/
    ├── test_ground_analogue.py
    ├── test_ground_context7.py
    ├── test_ground_template.py
    ├── test_ground.py
    ├── test_synthesize.py
    ├── test_validate.py
    ├── test_write_criteria.py
    └── fixtures/
        └── analogues/
            └── mini-flask-demo/       # vendored tiny Flask app for integration tests
```

Each file has one clear responsibility. Stage scripts share a small helper module (`scripts/synthesize/_common.py`) for JSON IO to `.skillgoid/synthesis/`.

## Testing strategy

**Unit tests (per stage script):**
- `test_ground_analogue.py` — reads vendored fixture repo, extracts expected observations.
- `test_ground_context7.py` — mocks context7 MCP calls; verifies query construction + observation parsing.
- `test_ground_template.py` — keyword matching, threshold behavior, template loading.
- `test_ground.py` — end-to-end Stage 1 with all three sources mocked; verifies `grounding.json` structure.
- `test_synthesize.py` — mocks subagent dispatch; verifies provenance-required parse, rejects hallucinated gates.
- `test_validate.py` — oracle run classification for each of the six table rows (pass/pass, pass/fail, fail, timeout, install-err); uses local fixture repos.
- `test_write_criteria.py` — renders known `validated.json` to expected `criteria.yaml` string.

**Integration test:**
- `test_synthesize_gates_e2e.py` — runs the full pipeline against `tests/fixtures/analogues/mini-flask-demo/`, mocks subagent dispatch (fixed gate set), asserts produced `criteria.yaml` has expected provenance labels and validation states.

**No live-LLM tests.** Synthesis subagent dispatch is mocked at the `subprocess.run(Task, ...)` boundary — tests feed fixed drafts.json back.

## Risks

- **Hallucinated gates slipping through provenance check.** Mitigation: Stage 2 parse rejects any draft without a `provenance.ref` matching an entry in `grounding.json`. Tests cover this explicitly.
- **Oracle validation takes too long on real-world analogues** (e.g., cloning a 500MB repo). Mitigation: total validation timeout (10 min), `--skip-validation` escape hatch, shallow clone by default.
- **Template library bitrot.** Initial authoring is a one-time cost; ongoing maintenance is bounded by how many domains we add. v1 keeps the list small (5 templates) to make this tractable.
- **context7 MCP unavailable at runtime.** Graceful skip — Stage 1b catches connection errors and proceeds with analogue + template sources only. Tests cover this path.
- **User-pointed analogue has test infrastructure we can't run** (requires credentials, Docker, specific OS). Mitigation: oracle validation degrades to `validated: none` per-gate with warn text; user sees which gates were unvalidated and decides.
- **`clarify` change breaks existing workflows that expect it to produce `criteria.yaml`.** Mitigation: existing hand-authored `criteria.yaml` files keep working (build doesn't inspect origin); only new projects go through the new path. Migration note for existing users: old projects keep running; new projects use synthesize-gates.

## Open questions for implementation

- Exact context7 MCP query shape — depends on current MCP interface when implementation starts. Resolve in Task 4 (Stage 1b).
- Template scoring threshold — initial guess: ≥2 keyword matches + language match. Tune empirically during integration testing.
- Subagent model selection for Stage 2 — default to Sonnet for synthesis (balance cost + quality); Opus if we see recurring gate-logic errors. Configurable via env var.
- Shallow clone depth for analogues — default to `--depth 1`, fallback to full clone if the user-pointed repo is a local path or fails shallow fetch.

## Success criteria (post-implementation)

A user with a rough goal and one analogue repo URL can run:

```
$ /skillgoid:clarify
(answers questions, goal.md written)

$ /skillgoid:synthesize-gates https://github.com/shlink/shlink
(Stage 1-4 run, criteria.yaml written with provenance comments)

$ $EDITOR .skillgoid/criteria.yaml
(trims or tweaks as desired)

$ /skillgoid:build
(loop executes against synthesized criteria)
```

...and the resulting `criteria.yaml` contains at least 3 gates with `validated: oracle` labels traceable to the analogue's test suite, with the overall synthesis completing in under 5 minutes wall-clock for a medium-sized analogue repo.
