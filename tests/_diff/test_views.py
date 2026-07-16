from pgmig._diff.views import _dependents_closure
from pgmig._keys import ViewKey

A = ViewKey("public", "a")
B = ViewKey("public", "b")
C = ViewKey("public", "c")


def test_dependents_closure_transitive() -> None:
    # Seed a; b reads a, c reads b -> closure is all three.
    assert _dependents_closure({A}, {B: {A}, C: {B}}) == {A, B, C}


def test_dependents_closure_handles_shared_dependents() -> None:
    # Both b and c read a (a diamond's top); c is reached once even though two paths lead
    # to it, exercising the already-seen skip.
    assert _dependents_closure({A}, {B: {A}, C: {A, B}}) == {A, B, C}
