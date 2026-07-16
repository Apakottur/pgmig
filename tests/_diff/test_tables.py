import pytest

from pgmig import PgmigUnsupportedError
from pgmig._diff.tables import _alter_shared_column, _column_def, _parenthesize_generation
from pgmig._models import Column


def _generated_column(name: str, *, generated: str, expression: str | None, not_null: bool = False) -> Column:
    """
    Build a generated Column ('s' stored or 'v' virtual) for the unit tests. Virtual columns
    only exist on PG18, so the virtual branches are exercised here rather than against a live DB.
    """
    return Column(
        name=name,
        type="integer",
        not_null=not_null,
        default=None,
        comment=None,
        identity="",
        serial_sequence=None,
        generated=generated,
        generation_expression=expression,
    )


def _alter(src: Column, dst: Column) -> tuple[list[str], list[str]]:
    """
    Call _alter_shared_column for a column present on both sides of table public.t, with no
    primary key involvement.
    """
    return _alter_shared_column(
        schema_name="public",
        table_name="t",
        column_name=src.name,
        src_column=src,
        dst_column=dst,
        pk_columns=set(),
        src_pk_columns=set(),
    )


def test_virtual_generated_column_emitted() -> None:
    """
    A virtual generated column (PG18+, attgenerated 'v') renders its GENERATED ALWAYS AS (...)
    VIRTUAL clause, with NOT NULL appended when set. Unit-tested on _column_def directly since a
    live virtual column only exists on PG18.
    """
    column = _generated_column("v", generated="v", expression="(b * 2)")
    assert _column_def(column) == '"v" integer GENERATED ALWAYS AS (b * 2) VIRTUAL'

    not_null_column = _generated_column("v", generated="v", expression="(b * 2)", not_null=True)
    assert _column_def(not_null_column) == '"v" integer GENERATED ALWAYS AS (b * 2) VIRTUAL NOT NULL'


def test_stored_generation_expression_change_drops_and_readds() -> None:
    """
    A STORED generated column whose expression changes is rebuilt with DROP COLUMN + ADD COLUMN
    (portable to pre-PG18, which has no in-place expression ALTER); its derived data recomputes.
    """
    src = _generated_column("doubled", generated="s", expression="(b * 2)")
    dst = _generated_column("doubled", generated="s", expression="(b * 3)")
    statements, deferred = _alter(src, dst)
    assert statements == [
        'ALTER TABLE "public"."t" DROP COLUMN "doubled";',
        'ALTER TABLE "public"."t" ADD COLUMN "doubled" integer GENERATED ALWAYS AS (b * 3) STORED;',
    ]
    assert deferred == []


def test_virtual_generation_expression_change_sets_expression() -> None:
    """
    A VIRTUAL generated column's expression is changed in place with SET EXPRESSION AS (...)
    (PG18 syntax); it has no stored data to rebuild.
    """
    src = _generated_column("vv", generated="v", expression="(b * 2)")
    dst = _generated_column("vv", generated="v", expression="(b * 5)")
    statements, deferred = _alter(src, dst)
    assert statements == ['ALTER TABLE "public"."t" ALTER COLUMN "vv" SET EXPRESSION AS (b * 5);']
    assert deferred == []


def test_generated_ness_flip_raises() -> None:
    """
    A plain column gaining generated-ness (or a generated column losing it) has no in-place
    ALTER and is potentially destructive, so it still raises.
    """
    plain = _generated_column("c", generated="", expression=None)
    stored = _generated_column("c", generated="s", expression="(b)")
    with pytest.raises(PgmigUnsupportedError, match="generated change"):
        _alter(plain, stored)


def test_stored_to_virtual_flip_raises() -> None:
    """
    Switching a generated column between STORED and VIRTUAL changes its storage and has no
    in-place ALTER, so it raises rather than mis-diff.
    """
    stored = _generated_column("c", generated="s", expression="(b * 2)")
    virtual = _generated_column("c", generated="v", expression="(b * 2)")
    with pytest.raises(PgmigUnsupportedError, match="generated change"):
        _alter(stored, virtual)


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
