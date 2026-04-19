# integration-retry fixture blueprint

## Architecture overview

Two-file bash library. `lib_a.sh` provides `fn_a`. `lib_b.sh` provides `fn_b`,
which internally calls `fn_a`. The integration check sources both and calls
both functions.

## lib_a

File: `src/lib_a.sh`
Responsibility: define `fn_a`.

## lib_b

File: `src/lib_b.sh`
Responsibility: define `fn_b`, which calls `fn_a` from lib_a.
