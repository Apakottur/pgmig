from pgmig._diff.functions import _topological_drop_order
from pgmig._keys import FunctionKey
from pgmig._models import Function


def _func(name: str, depends_on: set[FunctionKey]) -> Function:
    return Function(
        name=name,
        identity_arguments="",
        definition="",
        return_type="integer",
        kind="f",
        comment=None,
        owner="postgres",
        grants=frozenset(),
        has_dependents=True,
        dependents=(),
        depends_on_functions=frozenset(depends_on),
        depends_on_relations=frozenset(),
    )


TOP = FunctionKey("public", "top()")
MID = FunctionKey("public", "mid()")
MID1 = FunctionKey("public", "mid1()")
MID2 = FunctionKey("public", "mid2()")
LEAF = FunctionKey("public", "leaf()")


def test_drop_order_ignores_deps_outside_late_set() -> None:
    # top depends on a routine that is not itself dropped late: that edge is ignored, so
    # top has no in-set dependency and comes out on its own.
    outside = FunctionKey("public", "outside()")
    late = {TOP: ("public", _func("top", {outside}))}
    assert _topological_drop_order(late) == [TOP]
