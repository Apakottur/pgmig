from tests._api.generate_setup import GenerateSetup


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


def test_materialized_view_over_system_view_not_refused(gen_setup: GenerateSetup) -> None:
    """
    A matview reading a system catalog view (pg_stat_activity, a common monitoring pattern)
    must not trip the matview-dependency guard: system schemas are not managed by pgmig, so
    the dependency is not a matview-on-managed-view edge that needs ordering.
    """
    # pg_get_viewdef qualifies the column with the relation name on 14/15, bare on 16+.
    column = "pg_stat_activity.pid" if gen_setup.pg_major in (14, 15) else "pid"
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE MATERIALIZED VIEW active AS SELECT pid FROM pg_stat_activity"],
        diff=[f'CREATE MATERIALIZED VIEW "public"."active" AS SELECT {column}\n   FROM pg_stat_activity WITH NO DATA'],
    )


def test_materialized_view_over_extension_view_not_refused(gen_setup: GenerateSetup) -> None:
    """
    A matview reading an extension-owned view (pg_stat_statements, in the user's own public
    schema, a common setup) must not trip the matview-dependency guard: extension-owned
    relations are not diffed, so the referenced side always exists and needs no ordering.
    Its schema is not a system schema, so only the extension-ownership leg excludes it.
    """
    # pg_get_viewdef qualifies the column with the relation name on 14/15, bare on 16+; the
    # FROM relation is schema-qualified because introspection runs with an empty search_path.
    column = "pg_stat_statements.userid" if gen_setup.pg_major in (14, 15) else "userid"
    gen_setup.assert_diff(
        both=["CREATE EXTENSION pg_stat_statements"],
        src=[],
        # WITH NO DATA in the fixture: querying pg_stat_statements needs the preloaded library,
        # which the test server does not have; the unpopulated matview only needs the catalog.
        dst=["CREATE MATERIALIZED VIEW stats AS SELECT userid FROM pg_stat_statements WITH NO DATA"],
        diff=[
            f'CREATE MATERIALIZED VIEW "public"."stats" AS SELECT {column}'
            "\n   FROM public.pg_stat_statements WITH NO DATA"
        ],
    )


def test_materialized_view_on_materialized_view_raises(gen_setup: GenerateSetup) -> None:
    """
    A materialized view that reads from another materialized view is not supported yet
    (dependency ordering within the shared view phases).
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE MATERIALIZED VIEW base AS SELECT 1 AS x",
            "CREATE MATERIALIZED VIEW derived AS SELECT x FROM base",
        ],
        match="materialized view",
    )
