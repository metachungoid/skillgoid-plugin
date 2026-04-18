# Skillgoid v0.4 — Integration Polish & Unstick

- **Date:** 2026-04-18
- **Status:** Draft, pre-implementation
- **Supersedes:** nothing — extends v0.3
- **Scope:** Observed-ROI reprioritization of `docs/roadmap.md`'s v0.4 bucket, informed by the first real-world run of Skillgoid (jyctl, 2026-04-17). Four thematic additions.

---

## 1. Why this is different from the roadmap's predicted v0.4

The roadmap listed 11 v0.4 candidates across 5 buckets. The jyctl run (committed at `~/.claude/skillgoid/metrics.jsonl` line 1; artifacts at `/home/flip/Development/skillgoid-test/jyctl/.skillgoid/`) produced real evidence about which ones actually matter. The tallies:

| Roadmap item | Evidence from jyctl | v0.4 disposition |
|---|---|---|
| Plan refinement mid-build | Plan was correct, no replan needed on this project | **Push to v0.5** — still predicted-high but unvalidated |
| Pre-plan feasibility gate | Would have caught `python` not on PATH before iter 1 | **Include** |
| Unstick skill | No stall occurred; still predicted-high for autonomy | **Include** (speculative bet, cheap) |
| Rehearsal mode | Overlaps with feasibility | **Push** (feasibility covers most of it) |
| Parallel chunks | Throughput-only, 3-chunk project doesn't need it | **Push** |
| Polyglot | Large architectural lift, no demand | **Push** |
| `/skillgoid:stats` | metrics.jsonl has 1 line; a reader is cheap | **Include** |
| Tighter vault retrieval | Vault has 1 entry, not a scale problem yet | **Push** |
| More adapters | No demand | **Push** |
| Gate type plugins | Premature | **Push** |
| Dashboards | Need more data first | **Push** |

**New items surfaced by the real run** that weren't in the roadmap:

| Item | Evidence | v0.4 disposition |
|---|---|---|
| Gate `env:` field | `cli-command-runs` couldn't pass PYTHONPATH → integration-gate workaround required | **Include** |
| Python binary auto-resolution | `python` vs `python3` PATH mismatch forced first integration attempt to fail | **Include** |
| Default `.gitignore` in scaffold | jyctl's first iteration committed `__pycache__/*.pyc` | **Include** |
| Clarify caveat on subprocess coverage | cli chunk wasted an iteration on a well-known pytest-cov limitation | **Include** (doc change only) |

## 2. Non-goals (explicit pushes to v0.5+)

- **Plan refinement mid-build** — still the single biggest predicted complexity-ceiling lever, but zero jyctl-evidence and the architectural risk is high (mutable plan during execution). v0.5 after more real runs.
- **Parallel chunks** — throughput-only on multi-chunk projects. No evidence we need it yet.
- **Polyglot / multi-language projects** — waits for a real full-stack project to demand it.
- **Rehearsal mode** — subsumed by pre-plan feasibility. If feasibility proves insufficient, revisit.
- **Tighter vault retrieval** — no scale pressure yet.
- **Dashboards / HTML rendering** — scaffolding isn't there. `/skillgoid:stats` markdown output is enough until `metrics.jsonl` has 20+ entries.
- **More language adapters** — ecosystem work waits for real demand.
- **Gate type plugins** — premature abstraction.

## 3. Core components

### 3.1 Gate `env:` field

The `cli-command-runs` and `run-command` handlers already accept a `command:` list. v0.4 adds an optional `env:` dict that's merged into `os.environ` when the subprocess spawns.

**Schema addition** (gate items in both `gates[]` and `integration_gates[]`):

```yaml
- id: cli_smoke
  type: cli-command-runs
  command: ["python3", "-m", "jyctl", "--help"]
  env:
    PYTHONPATH: "src"
  expect_exit: 0
```

**Handler change** — in `measure_python.py`, `_gate_cli_command_runs` and `_gate_run_command` read `gate.get("env") or {}` and merge into the env passed to `subprocess.run`. The merged env overrides existing values (user-defined wins). Relative paths in env values are interpreted relative to the project dir (so `PYTHONPATH: "src"` resolves to `<project>/src`).

**Why it matters:** the jyctl integration gate required `PYTHONPATH=src` to find the `jyctl` module. v0.3 offered no way to express this in `criteria.yaml` — users had to `pip install -e .` or pre-set env externally. With `env:`, criteria.yaml fully captures gate invocation.

### 3.2 Python binary auto-resolution

`cli-command-runs` and `run-command` handlers inspect `command[0]`. If it equals the literal string `"python"`, replace it with `sys.executable` before dispatch. Any other value (including `"python3"`, absolute paths, or other executables) passes through unchanged.

**Why it matters:** `python` isn't on every PATH (modern Debian/Ubuntu, minimal containers, some Python installations). jyctl's integration gate hit this. The fix is one line but eliminates a class of portability errors.

**Opt-out:** if a user truly needs bare `python` from PATH (e.g., to distinguish a system Python from a venv Python), they set `env: {SKILLGOID_PYTHON_NO_RESOLVE: "1"}` — and the handler respects it. Niche case, documented but not foregrounded.

### 3.3 Pre-plan feasibility skill

New skill `feasibility` invoked by `build` between `clarify` and `plan`. Its job: run each proposed gate's command (in a read-only, no-code-written way) to verify it *can* run in the current environment. Surfaces mismatches before any iteration budget burns.

**Procedure:**

1. Read `.skillgoid/criteria.yaml`.
2. For each gate, categorize by type:
   - `pytest`, `ruff`, `mypy`, `coverage` — check the tool is installed (`_resolve_tool(name)` from v0.2).
   - `import-clean` — check the `module` field is a plausible package name (alphanumeric + dots/underscores, not empty).
   - `cli-command-runs`, `run-command` — attempt the command with `--help` or equivalent, or at minimum check `command[0]` is resolvable on PATH / via `env:`.
3. For each gate, also check its `env:` keys make sense (warn if `PYTHONPATH: "src"` but no `src/` directory exists in project).
4. Emit a structured report: `{checks: [{gate_id, ok: bool, hint: str}], all_ok: bool}`.
5. If `all_ok == false`, show the user the mismatches and ask whether to fix criteria now, proceed anyway, or abort.

**What it doesn't do:** run tests, fetch dependencies, or exercise the full gate. It's a shallow pre-flight check, not a dry-run of the loop.

**When to use:** invoked by `build` automatically on fresh start (between clarify and plan). Also user-invokable directly: `/skillgoid:feasibility`.

### 3.4 Clarify improvements (observed caveats)

Small prose additions to `skills/clarify/SKILL.md`:

- **Default `.gitignore` proposal.** For Python projects, propose a minimal `.gitignore` (copied from the plugin's own template) if not present. Include `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.coverage`, `.venv/`, `*.egg-info/`, `build/`, `dist/`.

- **Coverage + CLI subprocess caveat.** When proposing a `coverage` gate alongside a `cli-command-runs` gate (typical CLI project), include a comment in the proposed `criteria.yaml`:
  ```yaml
  # NOTE: pytest-cov does not instrument subprocess calls.
  # Combine this coverage gate with in-process CLI tests that call
  # your main(argv) directly with monkeypatched sys.stdin/stdout,
  # not just subprocess-based tests.
  ```

### 3.5 Unstick skill

New skill `unstick` — user-invokable with `/skillgoid:unstick <chunk_id> "<one-sentence hint>"`.

**Procedure:**
1. Read `.skillgoid/chunks.yaml` to validate `chunk_id`.
2. Read the most recent iteration for this chunk from `.skillgoid/iterations/` — if `exit_reason` isn't `stalled` or `budget_exhausted`, ask user to confirm (not every chunk deserves an unstick).
3. Dispatch a fresh chunk subagent (same pattern as `build` step 3c) with the one-sentence hint injected via the `## Integration failure context` slot in the chunk prompt template (repurposing the v0.2 slot for general hints).
4. Continue the loop from there — the subagent picks up mid-flight with fresh context + hint + access to prior iterations.

**When to use:** the loop has stalled or budget-exhausted and the user has a specific one-sentence correction that would unblock the agent (e.g., "the API key lives in KEY_ENV_VAR, not API_KEY" or "use pytest-asyncio not plain pytest for the async tests").

**Why include despite no jyctl evidence:** the autonomy-preservation value is large even if rare. One hour of manual takeover vs. 30 seconds of hint-typing. Cheap to implement (one skill + existing dispatch machinery).

### 3.6 Build orchestrator: surface unstick hint on stall

Small addition to `skills/build/SKILL.md` step 3e (the gate check after a chunk subagent returns). When `exit_reason == "stalled"` or `"budget_exhausted"`, the error message surfaced to the user now includes:

```
Chunk <id> exited with <exit_reason> after <N> iterations.
Latest failure: <signature> — <brief summary>
Options:
  • /skillgoid:build resume — retry with same budget (only useful if env changed)
  • /skillgoid:build retrospect-only — finalize as-is
  • /skillgoid:unstick <id> "<one-sentence hint>" — re-dispatch with a human hint
```

Pure prose update. No code change.

### 3.7 `/skillgoid:stats` reader

New skill `stats`. Reads `~/.claude/skillgoid/metrics.jsonl` and produces a markdown summary.

**Sections in the output:**
- **Last N projects** (default 20): table of slug, date, outcome, chunks, iterations, stalls.
- **Rollups**: success rate, average iterations per chunk, stall rate, budget-exhaustion rate, integration-retry rate.
- **Failure-mode distribution**: fraction of projects hitting stall / budget-exhausted / integration-retries.
- **Language distribution**: projects per language.

**What it doesn't do:** dashboards, HTML, graphs. Markdown only. `stats` is a read-only skill — never modifies `metrics.jsonl`.

**Invocation:** `/skillgoid:stats` (defaults to last 20), `/skillgoid:stats 100` (last 100).

## 4. Data layout

### 4.1 `criteria.yaml` schema additions

Gate items (both `gates[]` and `integration_gates[]`) gain:

```yaml
env:
  type: object
  additionalProperties: {type: string}
  description: "Optional environment variables merged into os.environ when running this gate."
```

No other schema changes.

### 4.2 No new directories

All v0.4 additions slot into existing file layout:
- `scripts/measure_python.py` — adds env handling + python resolution.
- `skills/feasibility/SKILL.md` — new skill (prose).
- `skills/unstick/SKILL.md` — new skill (prose).
- `skills/stats/SKILL.md` — new skill (prose).
- `scripts/stats_reader.py` — helper that does the metrics.jsonl aggregation (loaded by `stats` skill).
- `skills/build/SKILL.md`, `skills/clarify/SKILL.md` — prose updates.

## 5. Skill-level changes

- `skills/build/SKILL.md` — insert `skillgoid:feasibility` step between `clarify` and `plan` (main-session prep, step 2 extension); update stall/budget exit message to surface `/skillgoid:unstick`.
- `skills/clarify/SKILL.md` — add `.gitignore` proposal step + subprocess-coverage caveat comment.
- `skills/feasibility/SKILL.md` — new, procedure per §3.3.
- `skills/unstick/SKILL.md` — new, procedure per §3.5.
- `skills/stats/SKILL.md` — new, procedure per §3.7.
- `skills/python-gates/SKILL.md` — tiny note that `env:` is honored.
- `skills/retrieve/SKILL.md`, `skills/plan/SKILL.md`, `skills/loop/SKILL.md`, `skills/retrospect/SKILL.md` — unchanged.

## 6. Testing strategy

- **`env:` field tests** — 3 tests: env passed through, env overrides outer, invalid env type rejected by schema.
- **Python resolution tests** — 2 tests: bare `python` → `sys.executable`, `python3` untouched.
- **Feasibility helper tests** — 5 tests: missing tool detection, unresolvable `command[0]`, import-clean module format check, PYTHONPATH-but-no-src detection, all-ok happy path.
- **Stats reader tests** — 4 tests: empty metrics, 1-line metrics, multi-line with mixed outcomes, non-existent file handled.
- **No runtime test** for unstick, feasibility, stats *skills* themselves — they're prose consumed by Claude at runtime. Schema/helper tests cover the measurable parts.

**Expected test count:** 80 (v0.3) + ~14 new = ~94 total.

## 7. Backward compatibility

Fully additive:
- Missing `env:` on a gate → no env overrides, same as v0.3.
- Missing `feasibility` step in build — the main-session prep just runs `clarify` → `plan` directly (same as v0.3). New installations get the feasibility step; existing mid-project runs resuming under v0.4 use v0.3 flow because the skill invocation chain is driven by build's current-version prose.
- Missing `unstick` skill invocation — users of v0.3 ignore it; no disruption.
- Missing `stats` — never invoked implicitly.

No migration required. v0.3 projects resumed under v0.4 continue cleanly.

## 8. Complexity budget

Estimated plan size: ~12 tasks.

- Env field (schema + measure_python + tests): 1 task
- Python resolution (measure_python + tests): 1 task
- Feasibility skill + schema checks helper + tests: 2 tasks
- Build orchestrator wires feasibility: 1 task
- Build stall-message surfaces unstick: 1 task (prose)
- Clarify prose (gitignore + coverage caveat): 1 task
- Unstick skill: 1 task (prose)
- Stats reader helper + tests: 1 task
- Stats skill: 1 task (prose)
- Python-gates prose note for env: 1 task
- Docs (README, CHANGELOG, roadmap): 1 task

## 9. Open questions (for planning pass)

1. **Feasibility's depth.** Should it actually invoke commands (e.g., run `ruff --version` to confirm availability) or just check binary existence? Leaning toward "binary exists + one lightweight invocation" per tool — balances coverage with speed.
2. **Feasibility as blocking or advisory.** When mismatches are found, does `build` auto-abort or ask? Leaning advisory with explicit user confirmation to proceed.
3. **`.gitignore` proposal — overwrite existing?** Probably never. If `.gitignore` exists, suggest additions rather than replacement.
4. **Unstick on a chunk with budget exhausted — does it reset the attempt counter?** Yes — unstick implies a fresh attempt with new context, so attempts should start from 1 again (but cap total unstick invocations per chunk at 3 to prevent runaway).
5. **Stats output format — when are tables appropriate vs. summaries?** Rollups as text, last-N-projects as markdown table. Cap table at 20 rows for readability; users can pass `N` for more.

## 10. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Feasibility false positives (command exists but fails under real conditions) | Medium | Advisory only — user can override. |
| Feasibility false negatives (command doesn't exist but check passes) | Low | Next iteration catches it. |
| `env:` field misuse (shell-injection style payloads) | Low | Values are passed to subprocess as env dict, not shell. Python subprocess API escapes cleanly. |
| Python resolution breaks users who genuinely want bare `python` | Low | Opt-out via `SKILLGOID_PYTHON_NO_RESOLVE=1` in `env:`. |
| Unstick context injection confuses the subagent | Medium | Use the established `## Integration failure context` slot pattern from v0.2 — proven to work for auto-repair. |
| Stats reader crashes on malformed metrics.jsonl lines | Low | Parse line-by-line with try/except; skip malformed, continue. |

## 11. Definition of done

v0.4 ships when:

- All v0.3 tests still pass (80).
- New tests pass (~14 new, ~94 total).
- `/skillgoid:feasibility` runs on a representative criteria.yaml and produces a readable report.
- `/skillgoid:stats` reads the existing `~/.claude/skillgoid/metrics.jsonl` and produces the summary format.
- `/skillgoid:unstick` prose is complete enough that a user can self-invoke.
- README gets a "What's new in v0.4" section.
- CHANGELOG adds `[0.4.0]` entry.
- Roadmap marks v0.4 as shipped, updates v0.5 with the deferred items (plan refinement, rehearsal, parallel chunks, polyglot, dashboards, more adapters, gate plugins).
