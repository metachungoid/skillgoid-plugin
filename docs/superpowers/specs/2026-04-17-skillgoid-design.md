# Skillgoid — Design Spec (v0)

- **Date:** 2026-04-17
- **Status:** Draft, pre-implementation
- **Successor to:** Chungoid (see `../../../chungoid/` and `../../../metachungoid/` reference checkouts)
- **Distribution target:** Public GitHub repo, installable as a Claude Code plugin/skill pack

---

## 1. Identity

**Skillgoid** is a Claude Code plugin that turns a rough project goal into a shipped codebase through a **criteria-gated build loop** with **compounding cross-project memory**.

**One-liner:** "Define success. Build. Measure. Reflect. Loop until gates pass. Learn across projects."

It is the successor concept to Chungoid, stripped of everything Claude Code now provides natively (MCP server, ChromaDB vector store, FastAPI transport, agent registry, YAML flow DSL, `.chungoid/project_status.json` locking) and rebuilt as a small composed set of skills that orchestrate Claude Code's own primitives (subagents, `TaskCreate`, `WebFetch`/`WebSearch`, plan mode, plugin hooks).

---

## 2. Why this exists

The original Chungoid (2024–2025) bet on a stage-based autonomous workflow backed by a vector reflection store. In 2026, several of its core bets are now native Claude Code features:

| Chungoid component | Replaced by |
|---|---|
| Reflection store in Chroma | File-based vault + Claude's in-context semantic reasoning |
| `a2a_agent_registry` → tool lookup | Claude Code subagents, Skill tool |
| `project_status.json` + filelock | `TaskCreate` / `TaskList` |
| Context7 library-doc retrieval | `WebFetch` / `WebSearch` |
| Stage prompt YAMLs loaded by `PromptManager` | Skill markdown files with frontmatter |
| Stdio MCP + FastAPI transports | Plugin installation + Skill tool invocation |
| Flow Executor + Stage-Flow DSL | Prompt-level loop pattern inside an orchestrator skill |

What's **not** natively replicated is the distinctive Chungoid behavior: a build process that **loops back** when validation fails, and a memory store that **compounds across projects**. Those are what Skillgoid ships.

---

## 3. Core concept

Three properties distinguish Skillgoid from "just use Claude Code":

1. **Success criteria are first-class.** Before building, the user declares measurable gates (tests, lint, typecheck, acceptance scenarios). Loop termination is defined in terms of these gates — **not** the agent's self-assessment of "done."
2. **Closed feedback loop.** Build a chunk → run gates → on fail, reflect on the failure signature and retry with that context → repeat until gates pass or a loop-break condition hits.
3. **Cross-project learnings vault.** Reflections from every project accumulate in a user-global vault. New projects retrieve relevant past lessons before planning ("last 4 FastAPI projects had migration breakage from X"). Memory compounds.

The "loop" is not runtime infrastructure — it is a **prompt pattern** embedded in the orchestrator skill's instructions. Claude follows the pattern naturally; no separate execution engine is required.

---

## 4. Architecture

```
┌───────────────────── skill-pack (GitHub repo) ─────────────────────┐
│                                                                     │
│  CORE SKILLS (language-agnostic)                                    │
│   ├─ skillgoid              top-level orchestrator, user-invoked   │
│   ├─ skillgoid-clarify      interactive goal + criteria definition │
│   ├─ skillgoid-plan         design blueprint + chunk breakdown     │
│   ├─ skillgoid-loop         build ▸ measure ▸ reflect inner loop   │
│   ├─ skillgoid-retrieve     query vault for relevant past lessons  │
│   └─ skillgoid-retrospect   end-of-project summary + vault write   │
│                                                                     │
│  GATE ADAPTERS (per-language, pluggable)                            │
│   └─ skillgoid-adapter-python   (v0 ships with this one)           │
│      (adapter-node, adapter-go, etc. in v1+)                       │
│                                                                     │
│  HOOKS (declared in plugin manifest if supported, else opt-in)      │
│   ├─ SessionStart: skillgoid-detect-resume                         │
│   └─ Stop:         skillgoid-gate-guard                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Layer separation

- **Core skills** own workflow, prompts, and the loop pattern. They contain no language-specific logic.
- **Gate adapters** own measurement. Each adapter knows how to run one language's toolchain and return a structured gate report.
- **Hooks** own safety/continuity. They are not required for correctness but prevent common failure modes.

---

## 5. Data layout

### Project-local (`.skillgoid/` at the target project root)

- `goal.md` — refined goal statement, written by `skillgoid-clarify`
- `criteria.yaml` — structured gates + free-form acceptance scenarios
- `blueprint.md` — design + interface definitions, written by `skillgoid-plan`
- `chunks.yaml` — ordered list of build chunks with per-chunk gate subsets
- `iterations/NNN.json` — per-iteration record: chunk id, attempt number, gate results, reflection text, timestamp
- `retrospective.md` — written at end of project by `skillgoid-retrospect`

### User-global vault (`~/.claude/skillgoid/vault/`)

- `learnings/YYYY-MM-DD-<project-slug>/reflection.md` — one markdown file per *notable* reflection promoted from a finished project
- `index.jsonl` — append-only metadata index: `{slug, date, languages, tags, outcome, keywords, reflection_path}` — used for fast filtering before semantic scan

**No Chroma, no vector DB, no embeddings.** Retrieval uses Claude's own in-context reasoning over *filtered* files: the jsonl index narrows candidates by language/tags/keywords, then Claude reads the surviving reflections and decides which are relevant. Rationale:

- Zero install burden for end users (the killer issue with the Chungoid Chroma dependency).
- Plain markdown is user-inspectable, grep-able, and optionally git-trackable.
- Small-scale retrieval quality is fine without vector search — projects are tagged, not enumerated in the thousands.

---

## 6. Control flow

```
  user: /skillgoid build <rough goal>
         │
         ▼
  ┌─────────────────────────────┐
  │ skillgoid-retrieve           │  surface top-K past learnings
  └─────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────┐
  │ skillgoid-clarify            │  interactive; writes goal.md + criteria.yaml
  └─────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────┐
  │ skillgoid-plan               │  writes blueprint.md + chunks.yaml
  └─────────────────────────────┘
         │
         ▼
  for each chunk in chunks.yaml:
       ┌─────────────────────────────┐
       │ skillgoid-loop               │  build ▸ adapter-measure ▸ reflect
       │   while gates fail AND       │  writes iterations/NNN.json each pass
       │         attempts < max AND   │
       │         progress != stalled  │
       └─────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────┐
  │ skillgoid-retrospect         │  retrospective.md + vault promotion
  └─────────────────────────────┘
```

---

## 7. Gate adapter contract

A **gate adapter** is a skill that, when invoked with a project path and the current `criteria.yaml`, returns a structured JSON report:

```json
{
  "passed": false,
  "results": [
    {
      "gate_id": "pytest",
      "passed": false,
      "stdout": "...",
      "stderr": "...",
      "hint": "2 tests failed in test_auth.py — likely missing session fixture"
    }
  ]
}
```

That is the entire contract. Users write custom adapters by following a one-page markdown template committed to the repo.

### `skillgoid-adapter-python` v0 — built-in gate types

- `pytest` — runs pytest with optional path/filter args
- `ruff` — runs ruff check
- `mypy` — runs mypy (optional, gated on presence of `py.typed` or `mypy.ini`)
- `import-clean` — imports the top-level package without error
- `cli-command-runs` — runs an arbitrary CLI command and checks exit code + optional stdout regex
- `run-command` — generic escape hatch: any shell command, any expected exit code

Each gate type accepts parameters via `criteria.yaml`.

Example `criteria.yaml`:

```yaml
loop:
  max_attempts: 5
gates:
  - id: pytest
    type: pytest
    args: ["-q"]
  - id: lint
    type: ruff
  - id: cli_help
    type: cli-command-runs
    command: ["myapp", "--help"]
    expect_exit: 0
    expect_stdout_match: "Usage:"
acceptance:
  - "Given a user with no auth token, when they call /protected, they get 401"
  - "The CLI runs end-to-end on a fresh clone with only `pip install -e .`"
```

`acceptance` entries are **free-form scenarios** that the loop treats as soft gates: Claude reasons about them and writes/updates tests to cover them, but they don't block on literal string match.

---

## 8. Hooks

Two hooks materially improve reliability. Both are declared in the plugin manifest if the Claude Code plugin system supports it at ship time; if not, the README documents a one-time opt-in install via `settings.json`.

### 8.1 `skillgoid-detect-resume` — `SessionStart`

- **When:** every Claude Code session start.
- **What:** checks if CWD contains `.skillgoid/`. If yes, reads `chunks.yaml` + the latest `iterations/NNN.json` and injects a one-paragraph resume summary into the session context — current chunk, attempt number, last gate failure signature, remaining loop budget.
- **Why:** Claude doesn't auto-know it's resuming an in-progress Skillgoid project. Without this hook, the user has to re-brief every session; with it, resumption is seamless.

### 8.2 `skillgoid-gate-guard` — `Stop`

- **When:** Claude is about to stop while an active Skillgoid session has an unfinished chunk.
- **What:** reads current chunk's latest gate report. If any gate is failing AND loop budget remains AND no explicit user-break was requested, emits a blocking reminder: `Gates still failing: [list]. Loop budget remaining: N. Continue iterating or break explicitly.`
- **Why:** enforces the criteria-loop invariant — don't declare "done" while gates are red. Catches the failure mode where Claude ends the turn prematurely and the user doesn't realize the build is in a half-finished state.

### 8.3 Explicitly **NOT** hooked

- **`PostToolUse` on every `Edit`** — too noisy; duplicates the measure step; gates would run hundreds of times per chunk.
- **`UserPromptSubmit`** — injecting vault context on every turn is heavy and mostly irrelevant after the initial retrieval.
- **`PreToolUse` blockers** — hostile UX for little marginal safety.

---

## 9. Loop-break conditions

`skillgoid-loop` exits the inner loop when **any** of the following is true:

1. **Success:** all *structured* gates for the current chunk pass. (Acceptance scenarios from §7 are soft — they inform test-writing during the loop but do not block exit.)
2. **Budget exhausted:** `max_attempts` reached (default 5, configurable per-project in `criteria.yaml → loop.max_attempts`).
3. **No-progress stall:** two consecutive iterations produce the same failing-gate signature (same gate IDs failing with substantively identical error hints). The loop hands control back to the user with a stall summary rather than thrashing.
4. **User interruption:** standard Claude Code interrupt.

Each of these writes a terminal entry to `iterations/NNN.json` recording *which* exit condition fired.

---

## 10. Distribution

- GitHub repo (name TBD — `skillgoid` if available, else `skillgoid-plugin`).
- Claude Code plugin manifest at repo root with skills + hooks registered.
- `README.md` with:
  - Install command (one line).
  - 60-second quickstart ending in a working loop.
  - How to write custom gate adapters (one-page template).
  - How the vault works and where files live.
  - Link to this spec for design rationale.
- Semver-tagged releases; changelog per release.
- AGPL-3.0 or MIT license (decide at ship; Chungoid used AGPL — lean toward MIT for adoption unless the user has a reason to keep AGPL).

---

## 11. Out of scope (YAGNI v0)

- ChromaDB, vector stores, embeddings — replaced by filtered markdown + in-context semantic scan.
- MCP server, stdio/HTTP transports — skills *are* the integration.
- FastAPI / uvicorn / any web framework.
- Agent registry with `AgentCard`s — Claude Code subagents and `Skill` tool cover this.
- Stage-Flow DSL — replaced by the simpler `chunks.yaml`.
- Multi-language adapters beyond Python — v1+.
- Migration/compat tooling from old Chungoid projects — the old project is reference material, not a source of live users.
- Web UI / dashboard — terminal-only for v0.
- Telemetry / opentelemetry integration — the original had this; we don't need it to ship.

---

## 12. Defaults taken without explicit user sign-off

These are flagged so you can override in review:

| Default | Chosen value | Reason |
|---|---|---|
| Memory substrate | File-based vault (markdown + jsonl index) | Distribution friction of Chroma kills adoption |
| Criteria format | Structured YAML gates + free-form acceptance scenarios | Sharpest gates + human-readable |
| Default `max_attempts` | 5 | Balance between giving the loop room and not burning tokens |
| Project name | Skillgoid | Folder hint + continuity with Chungoid lineage |
| Top-level skill name | `skillgoid` | User invokes via `/skillgoid build <goal>` |
| v0 adapter | Python only | Sharpest toolchain; adapter pattern means v1+ scales cleanly |
| License | TBD (likely MIT) | Decide at ship |

---

## 13. Open questions (to resolve during planning)

1. **Plugin manifest hooks:** confirm current Claude Code plugin format supports declaring hooks at install, vs. requiring user `settings.json` edit. If not supported, the README-documented opt-in install is acceptable for v0.
2. **Vault retrieval strategy details:** the jsonl index filter criteria (tag taxonomy, language detection) and the top-K cap before in-context scan. Pick defaults during `writing-plans`.
3. **Subagent use:** should `skillgoid-loop` invoke a fresh subagent per chunk to isolate context, or run in the main session? Subagent isolation is cleaner but loses in-session continuity. Probably subagent-per-chunk.
4. **Stall detection heuristic:** the exact "substantively identical" comparison for repeated gate failures — hash of `(gate_id, first 200 chars of stderr)`? Needs spiking.
5. **Interactive clarify flow length:** how many rounds of Q&A is `skillgoid-clarify` allowed? Hard cap or agent-judgment?

---

## 14. Skill-by-skill behavior (appendix)

### 14.1 `skillgoid` (top-level orchestrator)

- **Trigger:** user runs `/skillgoid build <rough goal>` (or similar sub-commands: `status`, `resume`, `retrospect-only`).
- **Behavior:** chooses the next sub-skill based on project state (`.skillgoid/` presence, chunks remaining, gates passing). Acts as a router + progress reporter.

### 14.2 `skillgoid-clarify`

- **Trigger:** explicitly by orchestrator, or standalone by user for goal-refinement.
- **Behavior:** interactive Q&A bounded by a small number of clarifying turns. Produces `goal.md` + `criteria.yaml`. Asks user to review both before proceeding.

### 14.3 `skillgoid-plan`

- **Trigger:** explicitly by orchestrator after clarify.
- **Behavior:** writes `blueprint.md` (architecture, interfaces, data model) and `chunks.yaml` (ordered sequence of build chunks, each with a gate subset from `criteria.yaml`). Leverages Claude's plan mode if available.

### 14.4 `skillgoid-loop`

- **Trigger:** explicitly by orchestrator per chunk.
- **Behavior:** runs the inner build → measure → reflect cycle for one chunk until a loop-exit condition fires. Invokes the correct gate adapter based on `chunks.yaml` language tag. Writes `iterations/NNN.json` each pass. Reflects to `iterations/NNN.json` on each failure with specific, actionable learning notes.

### 14.5 `skillgoid-retrieve`

- **Trigger:** by orchestrator at project start; also invokable explicitly mid-project (e.g., "pull lessons about auth from past projects").
- **Behavior:** filters `~/.claude/skillgoid/vault/index.jsonl` by language/tags/keywords derived from the user's rough goal, reads top-K surviving reflections, summarizes relevance to the current project, and injects the summary into context.

### 14.6 `skillgoid-retrospect`

- **Trigger:** by orchestrator after all chunks pass their gates (or on explicit user request if the project was abandoned).
- **Behavior:** writes `retrospective.md`. **Promotes notable reflections** from `iterations/*.json` to `~/.claude/skillgoid/vault/learnings/YYYY-MM-DD-<slug>/reflection.md` + appends a new line to `index.jsonl`. "Notable" = reflections flagged during `skillgoid-loop` (e.g., failure modes encountered, unexpected interactions). Boring reflections stay project-local.

### 14.7 `skillgoid-adapter-python`

- **Trigger:** by `skillgoid-loop` when the current chunk's language tag is `python`.
- **Behavior:** runs the gate types listed in §7 and returns the structured report. Does **not** decide pass/fail policy — just reports. Policy lives in the loop skill.

### 14.8 Hooks

Covered in §8.
