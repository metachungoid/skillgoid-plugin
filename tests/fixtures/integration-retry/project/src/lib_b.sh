#!/usr/bin/env bash
# lib_b: defines fn_b (calls fn_a — deliberate typo: fn_a_typo)
fn_b() {
    fn_a_typo  # BUG: should be fn_a; fix by replacing fn_a_typo with fn_a
    echo "fn_b called"
}
