import pytest

from pgmig._diff._core import topological_sort
from pgmig._keys import RelationKey

A = RelationKey("public", "a")
B = RelationKey("public", "b")
C = RelationKey("public", "c")
D = RelationKey("public", "d")


def test_topological_sort_dependencies_first() -> None:
    # b depends on a, c depends on b -> a before b before c.
    assert topological_sort({A, B, C}, {B: {A}, C: {B}}) == [A, B, C]


def test_topological_sort_ignores_edges_outside_node_set() -> None:
    # b depends on a, but a is not in the node set: the edge is ignored, b has no in-set dep.
    assert topological_sort({B}, {B: {A}}) == [B]


def test_topological_sort_diamond() -> None:
    # b and c both depend on a; d depends on both. d is emitted only after both b and c.
    order = topological_sort({A, B, C, D}, {B: {A}, C: {A}, D: {B, C}})
    assert order[0] == A
    assert order[-1] == D
    assert order.index(B) < order.index(D)
    assert order.index(C) < order.index(D)


def test_topological_sort_ties_break_by_sorted_key() -> None:
    # No edges: pure tie-break order is the sorted node order, deterministically.
    assert topological_sort({C, A, B}, {}) == [A, B, C]


def test_topological_sort_diamond_ties_break_by_sorted_key() -> None:
    # After a is emitted, b and c are both ready (tie): they come out in sorted order,
    # so the full order is fully determined -- locks the smallest-first tie-break that the
    # heap must preserve.
    assert topological_sort({A, B, C, D}, {B: {A}, C: {A}, D: {B, C}}) == [A, B, C, D]


def test_topological_sort_cycle_raises() -> None:
    with pytest.raises(AssertionError, match="cycle"):
        topological_sort({A, B}, {A: {B}, B: {A}})
