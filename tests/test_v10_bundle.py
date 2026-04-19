"""End-to-end tests for v0.10 iteration contract bundle.

Locks in the v0.10 contract:
  - stall_check.signature() works with canonical object-form gate_report
  - metrics_append classifies budget_exhausted chunks as 'partial' outcome

These are lock-in tests. The behavior they assert shipped in v0.9; v0.10's
contribution is making the contract authoritative in skills/loop/SKILL.md prose.
If either test ever fails, the v0.10 contract has been broken.
"""
from scripts.stall_check import signature


def test_stall_signature_object_form_contract():
    """Test B: canonical object-form gate_report produces stable, discriminating signatures.

    Object form is {"passed": bool, "results": [...]} — the shape measure_python.py
    emits and the shape the v0.10 SKILL.md template documents. Same failing stderr
    across iterations must yield the same 16-char hex signature; different stderr
    must yield a different signature.
    """
    record = {
        "chunk_id": "parser",
        "iteration": 2,
        "gate_report": {
            "passed": False,
            "results": [
                {
                    "gate_id": "pytest_unit",
                    "passed": False,
                    "stderr": "FAILED tests/test_parser.py::test_dst - AssertionError",
                },
            ],
        },
        "failure_signature": "",
    }

    sig = signature(record)
    assert len(sig) == 16
    assert all(c in "0123456789abcdef" for c in sig), \
        f"signature must be lowercase hex: {sig!r}"

    # Same failure on a later iteration → same signature (stall detection).
    sig_next = signature({**record, "iteration": 3})
    assert sig == sig_next, "identical failing gate_report must produce identical signature"

    # Different failure → different signature.
    different = {
        **record,
        "gate_report": {
            "passed": False,
            "results": [
                {
                    "gate_id": "pytest_unit",
                    "passed": False,
                    "stderr": "FAILED tests/test_parser.py::test_leap - OverflowError",
                },
            ],
        },
    }
    assert signature(different) != sig, \
        "different failing stderr must produce different signature"
