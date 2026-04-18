# Skillgoid v0.8 Stress-Test Design — `minischeme`

**Status:** experiment design (not a feature spec)
**Date:** 2026-04-18
**Predecessor:** v0.7 Correctness Bundle (shipped same day)
**Purpose:** Run Skillgoid v0.7 against an 18-chunk single-language project (a Lisp-flavored interpreter) to surface the v0.8 priorities through observation rather than speculation.

## Why this experiment exists

The v0.7 retrospective identified that "polyglot language-support shape waits on 2-3 more polyglot project runs" — but that's the wrong axis to attack first. Two facts dominate the current evidence picture:

1. **Polyglot has 1 data point** (`taskbridge`). Synthetic polyglot stress tests are weak evidence; the real polyglot intake should come from organic user projects.
2. **Scale has 0 data points.** v0.5's parallel-wave feature was production-broken until v0.7. The v0.7 fix (per-chunk filenames + `paths:`-scoped commits + flock) was validated against waves of width 2 in the test suite. Nothing has stressed it at width 3+.

So this experiment focuses on the unknown that costs the least to investigate: scale. A clean single-language project at 18 chunks with at least one width-4 wave directly tests every v0.5 and v0.7 mechanism that has never seen production load.

## The target project — `minischeme`

A Lisp-flavored scripting language interpreter, implemented in Python 3.11+. Chosen because interpreters decompose naturally into many small, well-bounded modules; cross-chunk type contracts are real (AST → values → environment → evaluator → bytecode); the domain is hermetic (no external services); and end-to-end testability is trivial (run a source program, compare output).

### Language scope

- First-class functions with lexical-scope closures
- Numbers (int + float), booleans, strings, lists, hashmaps, nil
- Special forms: `if`, `cond`, `let`, `lambda`, `define`, `begin`, `set!`, `quote`, `try`/`throw`
- ~15 builtins across arithmetic, list ops, string ops, IO
- Tail-call optimization via trampoline
- Error handling with throw/try
- File-load / single-file modules (`load` form)
- REPL + script-execution CLI

### Out of scope

Macros, continuations, GC tuning, FFI, multi-source-file imports beyond `load`. Sufficient to be interesting; constrained to be shippable.

### The project's success criterion (NOT the experiment's)

Minischeme runs a corpus of ~10 example programs to expected output. This is *bonus* — even an aborted run produces v0.8 signal. The experiment succeeds based on findings, not on a working interpreter.

## Expected chunk decomposition (~18 chunks, 11 waves)

Drafted to maximize wave width without contrivance. Final shape will be set by `clarify` + `plan` during the actual run; deviations from this draft are themselves data points.

```
Wave 0 (1 chunk):   scaffold
Wave 1 (2 chunks):  errors, values
Wave 2 (2 chunks):  lexer, environment
Wave 3 (1 chunk):   parser
Wave 4 (1 chunk):   evaluator-core
Wave 5 (1 chunk):   special-forms
Wave 6 (4 chunks):  builtins-arith, builtins-list, builtins-string, builtins-io  ★
Wave 7 (2 chunks):  tail-calls, error-handling
Wave 8 (1 chunk):   modules
Wave 9 (2 chunks):  repl, cli
Wave 10 (1 chunk):  integration-examples
```

Total: **18 chunks, 11 waves, max width 4**. Wave 6 is the headline — if v0.7's flock + scoped-commit + `chunk_topo` machinery cracks anywhere, it cracks there.

## v0.8 hypotheses being tested

Each is a falsifiable claim. The experiment confirms or refutes via direct observation. Rejected hypotheses become v0.8 priorities.

| # | Hypothesis | Falsified by |
|---|---|---|
| H1 | v0.7's `_commit_lock` flock holds at width-4 concurrent commits | Cross-chunk file appearing in any wave-6 commit's diff |
| H2 | `chunk_topo.plan_waves` produces correct waves on an 18-chunk DAG | Manual graph review disagrees with output |
| H3 | The blueprint (passed verbatim to every subagent) stays under context budget at this scale | Subagent context-pressure errors / truncated output / ambiguous report |
| H4 | `vault_filter.py` keeps surfacing relevant lessons as `python-lessons.md` grows | A lesson that should have surfaced for a chunk did not |
| H5 | `max_attempts: 5` is enough across 18 chunks | Any chunk exits `budget_exhausted` |
| H6 | Cross-chunk type-contract failures surface within the responsible chunk's gates | A late-wave chunk fails because of an early-wave chunk's output shape |
| H7 | Plan-refinement-mid-build remains unneeded (zero evidence after 7 runs — does this 8th, larger run flip the verdict?) | Mid-run discovery of "the IR shape is wrong, replan needed" |
| H8 | `notable: true` curation rate stays sane (vault doesn't bloat) | >40% of iterations marked notable, OR `python-lessons.md` grows >2x |
| H9 | Iteration filename convention (`<chunk_id>-NNN.json`) holds with 18 chunks × ≥1 iteration each | Filename collision OR read-back failure in `metrics_append` / `gate-guard` |
| H10 | The flock helper degrades gracefully if a wave has 0 actual concurrency (single-chunk waves still work) | Single-chunk waves slow down or fail vs. baseline |

H7 is worth a special call-out: every prior retrospective has noted "no plan refinement need observed." A compiler-style project with mid-build IR-shape discovery is the canonical case where plan refinement *might* matter. If 18 chunks doesn't surface the need, that's strong evidence to formally close the question for v0.8 too.

## Methodology

### Driver

This same Claude session executes the procedure manually — interpreting `skills/*/SKILL.md` files and dispatching parallel subagents for waves via the `Agent` tool. Same driver pattern as the `taskbridge` polyglot run, so findings are comparable across experiments.

Subagents do real work: build code, run gates via `measure_python.py`, write iteration JSON files, commit via `git_iter_commit.py` (with `--chunks-file` + chunk `paths:` per the v0.7 contract). Each subagent does **one iteration per dispatch** (no full-loop unless explicitly needed) — keeps cost bounded and surfaces wave-level behavior cleanly.

### Working directory

`~/Development/skillgoid-test/minischeme/` — sibling to `taskbridge`. Starts empty; ends with a full git history of iteration commits, a populated `.skillgoid/` state dir, and a project-local `retrospective.md`.

### Findings collection

Append-only `~/Development/skillgoid-test/v0.8-findings.md`, mirroring the v0.7-findings.md format:
- Sequential finding IDs (F1, F2, …)
- Severity tier (🔴 blocking / 🟡 friction / 🟢 minor)
- Each finding linked back to the falsifying hypothesis where applicable

### Phase log

Same format as v0.7-findings.md's "Phase log" section: timestamped subsections per phase (retrieve, clarify, feasibility, plan, each wave, integration, retrospect) recording what happened and what surprised.

## Stopping criteria

Stop and retrospect when ANY of the following triggers:

1. **Wave 6 (the 4-way parallel headline) completes successfully.** This is the most important v0.8 datapoint. Successful completion of wave 6 means v0.7's parallel-wave machinery holds at width-4 — confirmation of H1 and H10 in one go. Stop here even if the language isn't done.
2. **A 🔴 blocking finding** that prevents further progress.
3. **5+ 🟡 findings accumulated.** Enough signal to spec v0.8 from; further chunks would mostly re-confirm.
4. **Wave 10 (integration) completes successfully.** Full success — interpreter actually works end-to-end.
5. **Iteration budget exhaustion across 3+ chunks.** Suggests max_attempts is wrong for this scale (H5 falsified) and continuing is wasteful.

We are NOT committed to shipping minischeme. We're committed to producing v0.8 evidence.

## Outputs

When the experiment stops:

- **`minischeme/.skillgoid/retrospective.md`** — project-local retrospective in the same shape as taskbridge's, with hypotheses-tested table and v0.8-prioritization recommendation.
- **`~/Development/skillgoid-test/v0.8-findings.md`** — full findings log with severities, methodology notes, and a synthesis section.
- **One JSON line in `~/.claude/skillgoid/metrics.jsonl`** — per `retrospect` SKILL.md, even partial runs append a metrics line.
- **A v0.8 prioritization recommendation** — analogous to the v0.7 retrospective's "ROI-ordered fix list," derived from which hypotheses got falsified.

## Anti-goals (things this experiment is NOT testing)

- Polyglot language support. (Different experiment, requires organic data.)
- v0.7 correctness fixes individually — those have unit tests; the stress run validates them under load, not from scratch.
- The plugin's installation / discovery / hooks. (Same setup as v0.7; assumed working.)
- Performance benchmarks. (Anecdotal, not measured.)

## What this spec is NOT

This is an **experiment design**, not a feature implementation spec. The plan that follows from this spec is an execution plan for the experiment (steps to actually run it), not an implementation plan for v0.8. The v0.8 implementation spec will be written *after* this experiment yields findings.

## Risk acknowledgment

The biggest risk: this experiment could surface ZERO new findings if v0.7 happens to hold cleanly. That would be a positive result, but it would leave v0.8 underspecified. Mitigation: the stopping criteria (#3, #4) ensure we generate *some* signal even in the smooth case, and the H7 plan-refinement question gets answered either way.

The second risk: the same-driver bias I noted in the v0.7 taskbridge retrospective — running the experiment as manual SKILL.md interpretation rather than via the installed plugin means some findings reflect "what the SKILL.md literally says" rather than "what the LLM-runtime-interpreting-it does in practice." Mitigated by being explicit about which findings are interpretation-only vs. observed-in-runtime.
