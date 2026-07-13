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


def _generate_and_converge(gen_setup: GenerateSetup) -> str:
    """
    Generate the migration, apply it to the source, and assert a re-diff is empty. Returns
    the generated SQL so the caller can assert statement ordering on it. Ordering is
    checked by relative position rather than exact SQL because pg_get_viewdef's whitespace
    for a multi-line view body varies across Postgres versions.
    """
    result = generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
    if result:
        gen_setup.src.execute(result)  # ty: ignore[invalid-argument-type]
        residual = generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
        assert residual == "", f"\nMigration did not converge.\nResidual diff:\n{residual}"
    return result


def test_view_on_view_create_ordering(gen_setup: GenerateSetup) -> None:
    """
    A view that reads another view is created after the view it reads.
    """
    gen_setup.dst.execute("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE VIEW derived AS SELECT x FROM base")

    result = _generate_and_converge(gen_setup)

    assert result.index('CREATE VIEW "public"."base"') < result.index('CREATE VIEW "public"."derived"')


def test_view_on_view_drop_ordering(gen_setup: GenerateSetup) -> None:
    """
    A view that reads another view is dropped before the view it reads.
    """
    gen_setup.src.execute("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.src.execute("CREATE VIEW derived AS SELECT x FROM base")

    result = _generate_and_converge(gen_setup)

    assert result.index('DROP VIEW "public"."derived"') < result.index('DROP VIEW "public"."base"')


def test_view_on_view_definition_change_cascades(gen_setup: GenerateSetup) -> None:
    """
    Changing the base view's definition drops and recreates it; the dependent view, though
    its own definition is unchanged, is dragged into the recreate (Postgres will not drop a
    view another view still reads). Drops go dependent-first, creates dependency-first.
    """
    gen_setup.execute_both("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE VIEW derived AS SELECT x FROM base")
    gen_setup.dst.execute("CREATE OR REPLACE VIEW base AS SELECT 2 AS x")

    result = _generate_and_converge(gen_setup)

    assert result.index('DROP VIEW "public"."derived"') < result.index('DROP VIEW "public"."base"')
    assert result.index('CREATE VIEW "public"."base"') < result.index('CREATE VIEW "public"."derived"')


def test_view_on_view_transitive_cascade(gen_setup: GenerateSetup) -> None:
    """
    A chain a <- b <- c: changing a recreates all three, ordered by the full dependency
    chain (drops c, b, a; creates a, b, c).
    """
    gen_setup.execute_both("CREATE VIEW a AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE VIEW b AS SELECT x FROM a")
    gen_setup.execute_both("CREATE VIEW c AS SELECT x FROM b")
    gen_setup.dst.execute("CREATE OR REPLACE VIEW a AS SELECT 2 AS x")

    result = _generate_and_converge(gen_setup)

    for name in ("a", "b", "c"):
        assert f'CREATE VIEW "public"."{name}"' in result
    assert (
        result.index('DROP VIEW "public"."c"')
        < result.index('DROP VIEW "public"."b"')
        < result.index('DROP VIEW "public"."a"')
    )
    assert (
        result.index('CREATE VIEW "public"."a"')
        < result.index('CREATE VIEW "public"."b"')
        < result.index('CREATE VIEW "public"."c"')
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

    result = _generate_and_converge(gen_setup)

    assert result.index('CREATE VIEW "a"."base"') < result.index('CREATE VIEW "b"."derived"')


def test_view_on_view_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical view-on-view chains on both sides -> no migration SQL.
    """
    gen_setup.execute_both("CREATE VIEW base AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE VIEW derived AS SELECT x FROM base")

    gen_setup.assert_migration_sql("")


def test_materialized_view_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A materialized view (relkind 'm'), even with an index on it, is not modelled yet and
    must raise rather than be silently ignored.
    """
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE INDEX report_x_idx ON report (x)")

    with pytest.raises(PgmigError, match=r"materialized view .* is not supported"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)
