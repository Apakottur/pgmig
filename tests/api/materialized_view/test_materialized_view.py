import pytest

from pgmig import PgmigError, generate
from tests.api.generate_setup import GenerateSetup


def test_materialized_view_create(gen_setup: GenerateSetup) -> None:
    """
    Materialized view present in target but missing in source -> CREATE (WITH NO DATA).
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        diff=['CREATE MATERIALIZED VIEW "public"."report" AS SELECT 1 AS x WITH NO DATA'],
    )


def test_materialized_view_drop(gen_setup: GenerateSetup) -> None:
    """
    Materialized view present in source but missing in target -> DROP.
    """
    gen_setup.assert_diff(
        src=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        dst=[],
        diff=['DROP MATERIALIZED VIEW "public"."report"'],
    )


def test_materialized_view_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical materialized view on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        src=[],
        dst=[],
        diff=[],
    )


def test_materialized_view_definition_change(gen_setup: GenerateSetup) -> None:
    """
    A changed materialized view definition -> drop and recreate.
    """
    gen_setup.assert_diff(
        src=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        dst=["CREATE MATERIALIZED VIEW report AS SELECT 2 AS x"],
        diff=[
            'DROP MATERIALIZED VIEW "public"."report"',
            'CREATE MATERIALIZED VIEW "public"."report" AS SELECT 2 AS x WITH NO DATA',
        ],
    )


def test_materialized_view_comment(gen_setup: GenerateSetup) -> None:
    """
    A materialized view comment is synced with COMMENT ON MATERIALIZED VIEW.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x", "COMMENT ON MATERIALIZED VIEW report IS 'hi'"],
        diff=[
            'CREATE MATERIALIZED VIEW "public"."report" AS SELECT 1 AS x WITH NO DATA',
            'COMMENT ON MATERIALIZED VIEW "public"."report" IS \'hi\'',
        ],
    )


def test_materialized_view_on_materialized_view_raises(gen_setup: GenerateSetup) -> None:
    """
    A materialized view that reads from another materialized view is not supported yet
    (dependency ordering within the shared view phases).
    """
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW base AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW derived AS SELECT x FROM base")

    with pytest.raises(PgmigError, match="materialized view"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
