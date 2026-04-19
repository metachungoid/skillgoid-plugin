#!/usr/bin/env bash
# Integration check: source both libs and invoke fn_a and fn_b.
# Fails when lib_b.sh has the fn_a_typo bug.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../src/lib_a.sh"
source "$SCRIPT_DIR/../src/lib_b.sh"
fn_a
fn_b
echo "integration check passed"
