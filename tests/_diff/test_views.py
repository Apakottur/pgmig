from pgmig._diff._core import dependents_closure
from pgmig._keys import RelationKey

A = RelationKey("public", "a")
B = RelationKey("public", "b")
C = RelationKey("public", "c")


def test_dependents_closure_handles_shared_dependents() -> None:
    # Both b and c read a (a diamond's top); c is reached once even though two paths lead
    # to it, exercising the already-seen skip.
    assert dependents_closure({A}, {B: {A}, C: {A, B}}) == {A, B, C}
