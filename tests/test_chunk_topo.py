"""Tests for scripts/chunk_topo.py — topological wave planner for parallel chunk dispatch."""
import pytest

from scripts.chunk_topo import CycleError, DependencyError, plan_waves


def test_empty_input():
    assert plan_waves([]) == []


def test_single_chunk_no_deps():
    chunks = [{"id": "scaffold"}]
    assert plan_waves(chunks) == [["scaffold"]]


def test_linear_chain_produces_n_waves_of_one():
    chunks = [
        {"id": "a"},
        {"id": "b", "depends_on": ["a"]},
        {"id": "c", "depends_on": ["b"]},
    ]
    waves = plan_waves(chunks)
    assert waves == [["a"], ["b"], ["c"]]


def test_independent_pair_in_same_wave():
    chunks = [
        {"id": "scaffold"},
        {"id": "parser", "depends_on": ["scaffold"]},
        {"id": "counters", "depends_on": ["scaffold"]},
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert set(waves[1]) == {"parser", "counters"}
    assert len(waves) == 2


def test_mdstats_shape_produces_five_waves():
    """mdstats: scaffold → [parser, counters] → aggregator → report → cli.
    Expected: 5 waves from 6 chunks."""
    chunks = [
        {"id": "scaffold"},
        {"id": "parser", "depends_on": ["scaffold"]},
        {"id": "counters", "depends_on": ["scaffold"]},
        {"id": "aggregator", "depends_on": ["counters"]},
        {"id": "report", "depends_on": ["aggregator"]},
        {"id": "cli", "depends_on": ["parser", "report"]},
    ]
    waves = plan_waves(chunks)
    assert len(waves) == 5
    assert waves[0] == ["scaffold"]
    assert set(waves[1]) == {"parser", "counters"}
    assert waves[2] == ["aggregator"]
    assert waves[3] == ["report"]
    assert waves[4] == ["cli"]


def test_missing_dependency_raises():
    chunks = [
        {"id": "a", "depends_on": ["does_not_exist"]},
    ]
    with pytest.raises(DependencyError, match="does_not_exist"):
        plan_waves(chunks)


def test_cycle_raises():
    chunks = [
        {"id": "a", "depends_on": ["b"]},
        {"id": "b", "depends_on": ["a"]},
    ]
    with pytest.raises(CycleError, match="cycle"):
        plan_waves(chunks)


def test_duplicate_chunk_ids_raises():
    chunks = [{"id": "a"}, {"id": "a"}]
    with pytest.raises(DependencyError, match="duplicate"):
        plan_waves(chunks)


def test_chunks_preserves_yaml_order_within_wave():
    """When two chunks are in the same wave, the output should be deterministic
    (sorted by id for stability)."""
    chunks = [
        {"id": "scaffold"},
        {"id": "zz", "depends_on": ["scaffold"]},
        {"id": "aa", "depends_on": ["scaffold"]},
    ]
    waves = plan_waves(chunks)
    assert waves[1] == ["aa", "zz"]  # sorted


def test_overlapping_paths_auto_serialize():
    """F8: chunks with overlapping paths in the same wave get split."""
    chunks = [
        {"id": "scaffold"},
        {"id": "a", "depends_on": ["scaffold"], "paths": ["src/shared.py"]},
        {"id": "b", "depends_on": ["scaffold"], "paths": ["src/shared.py", "src/b.py"]},
    ]
    waves = plan_waves(chunks)
    # a and b overlap on shared.py; must NOT be in same wave
    assert waves[0] == ["scaffold"]
    # Assert they're NOT both in the same wave
    assert not any("a" in w and "b" in w for w in waves)


def test_disjoint_paths_stay_parallel():
    """Regression: non-overlapping paths remain parallel (v0.5 behavior)."""
    chunks = [
        {"id": "scaffold"},
        {"id": "a", "depends_on": ["scaffold"], "paths": ["src/a.py"]},
        {"id": "b", "depends_on": ["scaffold"], "paths": ["src/b.py"]},
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert set(waves[1]) == {"a", "b"}
    assert len(waves) == 2


def test_three_way_overlap_produces_three_sub_waves():
    """All three chunks pairwise-overlap → three serial sub-waves."""
    chunks = [
        {"id": "scaffold"},
        {"id": "a", "depends_on": ["scaffold"], "paths": ["src/core.py"]},
        {"id": "b", "depends_on": ["scaffold"], "paths": ["src/core.py"]},
        {"id": "c", "depends_on": ["scaffold"], "paths": ["src/core.py"]},
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert waves[1:] == [["a"], ["b"], ["c"]]  # alphabetical order for determinism


def test_overlap_serialization_is_deterministic():
    """Alphabetical grouping produces identical waves across runs."""
    chunks = [
        {"id": "scaffold"},
        {"id": "z", "depends_on": ["scaffold"], "paths": ["src/shared.py"]},
        {"id": "a", "depends_on": ["scaffold"], "paths": ["src/shared.py"]},
        {"id": "m", "depends_on": ["scaffold"], "paths": ["src/shared.py"]},
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert waves[1:] == [["a"], ["m"], ["z"]]


def test_chunks_without_paths_dont_split():
    """Chunks that don't declare paths: remain parallel (v0.5 back-compat)."""
    chunks = [
        {"id": "scaffold"},
        {"id": "a", "depends_on": ["scaffold"]},  # no paths
        {"id": "b", "depends_on": ["scaffold"]},  # no paths
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert set(waves[1]) == {"a", "b"}
