# Skillgoid v0.6 — Shell-String Python Resolution

- **Date:** 2026-04-18
- **Status:** Draft, pre-implementation
- **Scope:** ONE item. Tightest release yet.
- **Spec predecessor:** v0.5 (Evidence-Driven Polish).

---

## 1. Why v0.6 is a micro-release

Four real Skillgoid runs (jyctl, taskq, mdstats, indexgrep — captured in `~/.claude/skillgoid/metrics.jsonl`) accumulated between v0.5 and v0.6. The evidence pattern is unambiguous:

- **4/4 projects** produced zero evidence that plan-refinement-mid-build is needed. At 3, 4, 6, AND 7 chunks. With AND without parallelizable waves. With AND without complex state (sqlite vs JSON). The hypothesis that the feature would have high value is not just unvalidated — it's contra-indicated by a consistent lack of triggering scenarios.
- **2/4 projects** hit integration-retry failures. **Both were `python` binary issues.** jyctl's was `python` not on PATH (v0.4 fixed `command[0]`). indexgrep's was bare `python` inside a `bash -c` shell string — which v0.4 does NOT handle because auto-resolution only applies to `command[0]`, not to substrings inside shell command bodies.

**The only item with new observed evidence is the shell-string python gap.** That's v0.6.

Everything else in the previous v0.6 roadmap stays deferred or gets demoted further. This is a one-item release on purpose — shipping what evidence supports, not what prediction suggests.

## 2. Non-goals (all demoted)

- **Plan refinement mid-build.** 4/4 runs, zero evidence. **Dropping from roadmap entirely** until a qualitatively different project shape (e.g., a research-grade build with genuine decomposition uncertainty) is tested. Two+ more runs without evidence should lock this in.
- **Parallel chunks (v0.5)** — already shipped, validated by indexgrep. No new work.
- **Polyglot.** 4/4 single-language projects.
- **Rehearsal mode.** Redundant with v0.4 feasibility + v0.5 scaffolding awareness.
- **Tighter vault retrieval.** 5 entries, no scale pressure.
- **More language adapters, gate-type plugins, dashboards.** No evidence.

## 3. The one component

### 3.1 `SKILLGOID_PYTHON` env export

**Problem:** v0.4's `_resolve_python` helper substitutes `command[0] == "python"` with `sys.executable`. This covers:

```yaml
command: ["python", "-m", "myproj"]   # v0.4 handles this
```

It does NOT cover:

```yaml
command: ["bash", "-c", "python -m myproj && python -m myproj_cli"]   # v0.4 fails
```

Real failure observed on indexgrep: `bash: line 1: python: command not found` → exit 127 → integration retry.

**Fix:** `scripts/measure_python.py`'s `_merge_env` helper always exports `SKILLGOID_PYTHON` (value: `sys.executable`) into the subprocess environment. Shell strings can reference `$SKILLGOID_PYTHON` and get a guaranteed working path:

```yaml
command: ["bash", "-c", "$SKILLGOID_PYTHON -m myproj && $SKILLGOID_PYTHON -m myproj_cli"]
env:
  PYTHONPATH: "src"
```

**Contract:**
- `SKILLGOID_PYTHON` is ALWAYS set by Skillgoid, to `sys.executable`. Outer `os.environ` values are overridden.
- User-provided gate `env:` CAN override it (rare use case: testing against a different interpreter).
- `_resolve_python`'s opt-out knob (`SKILLGOID_PYTHON_NO_RESOLVE: "1"`) continues to work for `command[0]`. The env export is separate and unconditional.

**Why env-var (not parse-bash-strings):**
1. Parsing `bash -c "..."` strings to substitute `python` → `sys.executable` is brittle (think quoted strings, subshells, backticks, heredocs).
2. An env var is a documented, discoverable contract users opt into by typing `$SKILLGOID_PYTHON`.
3. It also works for other shells (`sh`, `zsh`), inline `xargs`, etc. — no special-casing.

**Skill prose updates:**
- `skills/python-gates/SKILL.md` — add one-paragraph note documenting `SKILLGOID_PYTHON`.
- `skills/clarify/SKILL.md` — when proposing integration gates that use `bash -c` or similar shell pipelines, use `$SKILLGOID_PYTHON` instead of bare `python`.

## 4. Data-layout changes

None. No schema changes. No new files beyond tests.

## 5. Skill changes

- `scripts/measure_python.py` — `_merge_env` exports `SKILLGOID_PYTHON`. ~3 new lines.
- `skills/python-gates/SKILL.md` — one note paragraph.
- `skills/clarify/SKILL.md` — prose tweak to the integration-gate proposals for shell pipelines.
- All other skills unchanged.

## 6. Hooks

No changes.

## 7. Testing strategy

- 2 new tests in `tests/test_env_gate.py`:
  - `SKILLGOID_PYTHON` is exported to the subprocess env and equals `sys.executable`.
  - A shell string using `$SKILLGOID_PYTHON` resolves and executes successfully.

**Expected total:** 115 (v0.5) + 2 = 117.

## 8. Backward compatibility

Fully additive:
- Adding an env var to the merged environment breaks nothing (existing code ignores unused env vars).
- v0.5 criteria/chunks/iterations parse unchanged.
- User code that happens to read `SKILLGOID_PYTHON` would get a valid python path — Skillgoid didn't define the var before, so no migration risk.

## 9. Complexity budget

Estimated plan: ~4 tasks.

- Branch setup: 1 task (housekeeping).
- `_merge_env` exports SKILLGOID_PYTHON + tests: 1 task.
- Skill prose updates (python-gates + clarify): 1 task.
- Docs + plugin.json bump: 1 task.

## 10. Definition of done

- All v0.5 tests still pass (115).
- New tests pass (2). Total ~117.
- `SKILLGOID_PYTHON` is visible to any subprocess dispatched by run-command or cli-command-runs handlers.
- `plugin.json` bumped to `0.6.0` (must not forget — this was a v0.5 critical-fix lesson).
- README "What's new in v0.6" section.
- CHANGELOG `[0.6.0]` entry.
- Roadmap update: plan-refinement-mid-build formally dropped from roadmap (not just demoted); remaining v0.7+ items listed as "await qualitatively different project shapes."
