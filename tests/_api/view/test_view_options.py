import pytest

from tests._api.generate_setup import GenerateSetup


async def test_view_create_with_option(gen_setup: GenerateSetup) -> None:
    """
    A view carrying a reloption (security_barrier) is created with a WITH (...) clause.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE VIEW active WITH (security_barrier=true) AS SELECT 1 AS x"],
        diff=['CREATE VIEW "public"."active" WITH (security_barrier=true) AS SELECT 1 AS x'],
    )


async def test_view_option_added(gen_setup: GenerateSetup) -> None:
    """
    A view that gains a reloption -> drop and recreate. The definition is unchanged, so only
    the option difference forces the recreate.
    """
    await gen_setup.assert_diff(
        src=["CREATE VIEW active AS SELECT 1 AS x"],
        dst=["CREATE VIEW active WITH (security_barrier=true) AS SELECT 1 AS x"],
        diff=[
            'DROP VIEW "public"."active"',
            'CREATE VIEW "public"."active" WITH (security_barrier=true) AS SELECT 1 AS x',
        ],
    )


async def test_view_option_removed(gen_setup: GenerateSetup) -> None:
    """
    A view that loses a reloption -> drop and recreate back to a plain CREATE VIEW.
    """
    await gen_setup.assert_diff(
        src=["CREATE VIEW active WITH (security_barrier=true) AS SELECT 1 AS x"],
        dst=["CREATE VIEW active AS SELECT 1 AS x"],
        diff=[
            'DROP VIEW "public"."active"',
            'CREATE VIEW "public"."active" AS SELECT 1 AS x',
        ],
    )


async def test_view_option_unchanged(gen_setup: GenerateSetup) -> None:
    """
    An identical option on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE VIEW active WITH (security_barrier=true) AS SELECT 1 AS x"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_view_options_order_independent(gen_setup: GenerateSetup) -> None:
    """
    The same set of options written in a different order on the two sides is not a change:
    reloptions are stored in creation order, so the loader must normalize before comparing.
    security_invoker requires Postgres 15+.
    """
    if gen_setup.pg_major < 15:
        pytest.skip("security_invoker requires Postgres 15+")
    await gen_setup.assert_diff(
        src=["CREATE VIEW active WITH (security_invoker=true, security_barrier=true) AS SELECT 1 AS x"],
        dst=["CREATE VIEW active WITH (security_barrier=true, security_invoker=true) AS SELECT 1 AS x"],
        diff=[],
    )


async def test_view_check_option_added(gen_setup: GenerateSetup) -> None:
    """
    WITH CHECK OPTION is stored as the check_option reloption and emitted in the WITH clause.
    Needs an automatically-updatable view (a single table). pg_get_viewdef qualifies the
    column with the table name on Postgres 14-15.
    """
    column = "t.x" if gen_setup.pg_major in (14, 15) else "x"
    body = f"SELECT {column}\n   FROM public.t"
    await gen_setup.assert_diff(
        both=["CREATE TABLE t (x int)"],
        src=["CREATE VIEW active AS SELECT x FROM t"],
        dst=["CREATE VIEW active AS SELECT x FROM t WITH CASCADED CHECK OPTION"],
        diff=[
            'DROP VIEW "public"."active"',
            f'CREATE VIEW "public"."active" WITH (check_option=cascaded) AS {body}',
        ],
    )
