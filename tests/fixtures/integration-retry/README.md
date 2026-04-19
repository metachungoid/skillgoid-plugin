# integration-retry fixture

Language-agnostic reference fixture for Skillgoid's integration-retry path
(build/SKILL.md step 4g, addressed in v0.11).

## What it models

Two bash library chunks (`lib_a`, `lib_b`). Both pass per-chunk syntax-check
gates individually. The integration gate (`bash integration/check.sh`) fails
because `lib_b.sh` contains a deliberate typo: `fn_a_typo` instead of `fn_a`.
The pre-seeded `integration/1.json` records this failure — its stderr mentions
`src/lib_b.sh`, so `integration_suspect.py` correctly identifies `lib_b` as
the suspect chunk.

## Using it in tests

Copy `project/` to `tmp_path`, run `integration_suspect.py` against
`project/.skillgoid/integration/1.json`, assert `suspect_chunk_id == "lib_b"`,
then fix the typo (simulating the loop subagent's retry) and rerun
`bash integration/check.sh` to assert it now passes.

See `tests/test_integration_retry_fixture.py`.

## Why bash / run-command gates

`run-command` is the cross-adapter common denominator: every language adapter
must support it. This fixture validates orchestrator logic without coupling to
any specific language adapter. It works identically once TypeScript or Go
adapters are added in future versions.
