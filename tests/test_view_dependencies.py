import pytest

from pgmig import PgmigError
from pgmig._diff.views import _dependents_closure, _topological_order
from pgmig._models import ViewKey
from tests.fixtures.generate_setup import GenerateSetup

# --- Unit tests for the pure ordering helpers ---------------------------------------------
# Postgres cannot create a view cycle or be coerced into some edge shapes, so these branches
# (cycle detection, the closure's already-seen skip) are exercised directly rather than
# through a live database.

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


# --- Integration tests: generated migration SQL -------------------------------------------


def _view_body(gen_setup: GenerateSetup, table: str, from_ref: str) -> str:
    """
    Get the view body, depending on the Postgres major version.
    """
    match gen_setup.pg_major:
        case 14 | 15:
            column = f"{table}.x"
        case _:
            column = "x"
    return f"SELECT {column}\n   FROM {from_ref}"


def test_view_on_view_create_ordering(gen_setup: GenerateSetup) -> None:
    """
    A view that reads another view is created after the view it reads.
    """
    gen_setup.dst.execute("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE VIEW derived AS SELECT x FROM base")

    gen_setup.assert_migration_sql(
        [
            'CREATE VIEW "public"."base" AS SELECT 1 AS x;',
            f'CREATE VIEW "public"."derived" AS {_view_body(gen_setup, "base", "public.base")};',
        ]
    )


def test_view_on_view_drop_ordering(gen_setup: GenerateSetup) -> None:
    """
    A view that reads another view is dropped before the view it reads.
    """
    gen_setup.src.execute("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.src.execute("CREATE VIEW derived AS SELECT x FROM base")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "public"."derived";',
            'DROP VIEW "public"."base";',
        ]
    )


def test_view_on_view_definition_change_cascades(gen_setup: GenerateSetup) -> None:
    """
    Changing the base view's definition drops and recreates it; the dependent view, though
    its own definition is unchanged, is dragged into the recreate (Postgres will not drop a
    view another view still reads). Drops go dependent-first, creates dependency-first.
    """
    gen_setup.execute_both("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE VIEW derived AS SELECT x FROM base")
    gen_setup.dst.execute("CREATE OR REPLACE VIEW base AS SELECT 2 AS x")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "public"."derived";',
            'DROP VIEW "public"."base";',
            'CREATE VIEW "public"."base" AS SELECT 2 AS x;',
            f'CREATE VIEW "public"."derived" AS {_view_body(gen_setup, "base", "public.base")};',
        ]
    )


def test_view_on_view_transitive_cascade(gen_setup: GenerateSetup) -> None:
    """
    A chain a <- b <- c: changing a recreates all three, ordered by the full dependency
    chain (drops c, b, a; creates a, b, c).
    """
    gen_setup.execute_both("CREATE VIEW a AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE VIEW b AS SELECT x FROM a")
    gen_setup.execute_both("CREATE VIEW c AS SELECT x FROM b")
    gen_setup.dst.execute("CREATE OR REPLACE VIEW a AS SELECT 2 AS x")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "public"."c";',
            'DROP VIEW "public"."b";',
            'DROP VIEW "public"."a";',
            'CREATE VIEW "public"."a" AS SELECT 2 AS x;',
            f'CREATE VIEW "public"."b" AS {_view_body(gen_setup, "a", "public.a")};',
            f'CREATE VIEW "public"."c" AS {_view_body(gen_setup, "b", "public.b")};',
        ]
    )


def test_view_on_view_cross_schema(gen_setup: GenerateSetup) -> None:
    """
    A view-on-view dependency across schemas is ordered globally: the referenced view in
    one schema is created before the dependent view in another.
    """
    gen_setup.dst.execute("CREATE SCHEMA a")
    gen_setup.dst.execute("CREATE SCHEMA b")
    gen_setup.dst.execute("CREATE VIEW a.base AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE VIEW b.derived AS SELECT x FROM a.base")

    gen_setup.assert_migration_sql(
        [
            'CREATE SCHEMA "a";',
            'CREATE SCHEMA "b";',
            'CREATE VIEW "a"."base" AS SELECT 1 AS x;',
            f'CREATE VIEW "b"."derived" AS {_view_body(gen_setup, "base", "a.base")};',
        ]
    )


def test_view_on_view_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical view-on-view chains on both sides -> no migration SQL.
    """
    gen_setup.execute_both("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE VIEW derived AS SELECT x FROM base")

    gen_setup.assert_migration_sql("")
