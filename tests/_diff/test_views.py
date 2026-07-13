import pytest

from pgmig import PgmigError
from pgmig._diff.views import _dependents_closure, _topological_order
from pgmig._models import ViewKey

A = ViewKey("public", "a")
B = ViewKey("public", "b")
C = ViewKey("public", "c")


def test_topological_order_dependencies_first() -> None:
    # b reads a, c reads b -> a before b before c.
    order = _topological_order({A, B, C}, {B: {A}, C: {B}})
    assert order == [A, B, C]


def test_topological_order_ignores_edges_outside_node_set() -> None:
    # b reads a, but a is not in the node set: the edge is ignored and b has no in-set dep.
    order = _topological_order({B}, {B: {A}})
    assert order == [B]


def test_topological_order_diamond() -> None:
    # b and c both read a; d reads both b and c. d is emitted only after both of its
    # dependencies are, so discarding one dependency leaves d not-yet-ready.
    d = ViewKey("public", "d")
    order = _topological_order({A, B, C, d}, {B: {A}, C: {A}, d: {B, C}})
    assert order[0] == A
    assert order[-1] == d
    assert order.index(B) < order.index(d)
    assert order.index(C) < order.index(d)


def test_topological_order_cycle_raises() -> None:
    with pytest.raises(PgmigError, match="cycle"):
        _topological_order({A, B}, {A: {B}, B: {A}})


def test_dependents_closure_transitive() -> None:
    # Seed a; b reads a, c reads b -> closure is all three.
    assert _dependents_closure({A}, {B: {A}, C: {B}}) == {A, B, C}


def test_dependents_closure_handles_shared_dependents() -> None:
    # Both b and c read a (a diamond's top); c is reached once even though two paths lead
    # to it, exercising the already-seen skip.
    assert _dependents_closure({A}, {B: {A}, C: {A, B}}) == {A, B, C}
