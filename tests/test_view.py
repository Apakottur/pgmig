import pytest

from pgmig import PgmigError, generate
from tests.fixtures.generate_setup import GenerateSetup


def test_view_create(gen_setup: GenerateSetup) -> None:
    """
    View present in target but missing in source -> CREATE VIEW.
    """
    gen_setup.dst.execute("CREATE VIEW active AS SELECT 1 AS x")

    gen_setup.assert_migration_sql('CREATE VIEW "public"."active" AS SELECT 1 AS x;')


def test_view_drop(gen_setup: GenerateSetup) -> None:
    """
    View present in source but missing in target -> DROP VIEW.
    """
    gen_setup.src.execute("CREATE VIEW active AS SELECT 1 AS x")

    gen_setup.assert_migration_sql('DROP VIEW "public"."active";')


def test_view_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical view on both sides -> no migration SQL.
    """
    gen_setup.execute_both("CREATE VIEW active AS SELECT 1 AS x")

    gen_setup.assert_migration_sql("")


def test_view_definition_change(gen_setup: GenerateSetup) -> None:
    """
    A changed view definition -> drop and recreate.
    """
    gen_setup.src.execute("CREATE VIEW active AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE VIEW active AS SELECT 2 AS x")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "public"."active";',
            'CREATE VIEW "public"."active" AS SELECT 2 AS x;',
        ]
    )


def test_view_comment(gen_setup: GenerateSetup) -> None:
    """
    A view comment is synced with COMMENT ON VIEW.
    """
    gen_setup.dst.execute("CREATE VIEW active AS SELECT 1 AS x")
    gen_setup.dst.execute("COMMENT ON VIEW active IS 'hi'")

    gen_setup.assert_migration_sql(
        [
            'CREATE VIEW "public"."active" AS SELECT 1 AS x;',
            'COMMENT ON VIEW "public"."active" IS \'hi\';',
        ]
    )


def test_materialized_view_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A materialized view (relkind 'm'), even with an index on it, is not modelled yet and
    must raise rather than be silently ignored.
    """
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE INDEX report_x_idx ON report (x)")

    with pytest.raises(PgmigError, match=r"materialized view .* is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
