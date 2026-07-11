from tests.fixtures.generate_setup import GenerateSetup


def test_index_on_materialized_view_ignored(gen_setup: GenerateSetup) -> None:
    """
    An index on a materialized view (relkind 'm') must not crash introspection.
    Materialized views are out of scope, so no SQL is generated for it.
    """
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql("")
