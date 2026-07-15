from pgmig._diff.functions import _topological_drop_order
from pgmig._models import Function, FunctionKey


def _func(name: str, depends_on: set[FunctionKey]) -> Function:
    return Function(
        name=name,
        identity_arguments="",
        definition="",
        return_type="integer",
        kind="f",
        comment=None,
        has_dependents=True,
        depends_on_functions=frozenset(depends_on),
        depends_on_relations=frozenset(),
    )


TOP = FunctionKey("public", "top()")
MID = FunctionKey("public", "mid()")
MID1 = FunctionKey("public", "mid1()")
MID2 = FunctionKey("public", "mid2()")
LEAF = FunctionKey("public", "leaf()")


def test_drop_order_chain_dependent_first() -> None:
    # top -> mid -> leaf: a routine is dropped before the routines it depends on.
    late = {
        LEAF: ("public", _func("leaf", set())),
        MID: ("public", _func("mid", {LEAF})),
        TOP: ("public", _func("top", {MID})),
    }
    assert _topological_drop_order(late) == [TOP, MID, LEAF]


def test_drop_order_diamond_leaf_last() -> None:
    # top -> mid1, mid2 -> leaf: leaf, depended on by both mids, drops only after both.
    late = {
        LEAF: ("public", _func("leaf", set())),
        MID1: ("public", _func("mid1", {LEAF})),
        MID2: ("public", _func("mid2", {LEAF})),
        TOP: ("public", _func("top", {MID1, MID2})),
    }
    assert _topological_drop_order(late) == [TOP, MID1, MID2, LEAF]
