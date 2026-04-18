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
