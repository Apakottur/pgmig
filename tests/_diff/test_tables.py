import pytest

from pgmig._diff.tables import _column_def, _parenthesize_generation
from pgmig._models import Column


def test_virtual_generated_column_raises() -> None:
    """
    Virtual generated columns (PG18+, attgenerated 'v') are unsupported. Unit-tested on
    _column_def directly since a live virtual column only exists on PG18.
    """
    column = Column(
        name="v",
        type="integer",
        not_null=False,
        default=None,
        comment=None,
        identity="",
        serial_sequence=None,
        generated="v",
        generation_expression="(b * 2)",
    )

    with pytest.raises(NotImplementedError, match="Virtual generated column"):
        _column_def(column)


def test_parenthesize_generation_normalizes_to_one_pair() -> None:
    """
    The generation expression is wrapped in exactly one outer paren pair: an already-wrapping
    pair is stripped first, a bare/function expression is wrapped as-is, and a leading paren
    that does not span the whole expression is left in place.
    """
    assert _parenthesize_generation("(a * b)") == "(a * b)"  # already wrapped -> unchanged
    assert _parenthesize_generation("upper(x)") == "(upper(x))"  # function call -> wrapped
    assert _parenthesize_generation("b") == "(b)"  # bare column -> wrapped
    assert _parenthesize_generation("(a) + (b)") == "((a) + (b))"  # partial leading paren -> wrapped whole
