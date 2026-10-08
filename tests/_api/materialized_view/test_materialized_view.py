from tests._api.generate_setup import GenerateSetup


async def test_materialized_view_create(gen_setup: GenerateSetup) -> None:
    """
    Materialized view present in target but missing in source -> CREATE (WITH NO DATA).
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        diff=['CREATE MATERIALIZED VIEW "public"."report" AS SELECT 1 AS x WITH NO DATA'],
    )


async def test_materialized_view_drop(gen_setup: GenerateSetup) -> None:
    """
    Materialized view present in source but missing in target -> DROP.
    """
    await gen_setup.assert_diff(
        src=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        dst=[],
        diff=['DROP MATERIALIZED VIEW "public"."report"'],
    )


async def test_materialized_view_definition_change(gen_setup: GenerateSetup) -> None:
    """
    A changed materialized view definition -> drop and recreate.
    """
    await gen_setup.assert_diff(
        src=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        dst=["CREATE MATERIALIZED VIEW report AS SELECT 2 AS x"],
        diff=[
            'DROP MATERIALIZED VIEW "public"."report"',
            'CREATE MATERIALIZED VIEW "public"."report" AS SELECT 2 AS x WITH NO DATA',
        ],
    )


async def test_materialized_view_comment(gen_setup: GenerateSetup) -> None:
    """
    A materialized view comment is synced with COMMENT ON MATERIALIZED VIEW.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x", "COMMENT ON MATERIALIZED VIEW report IS 'hi'"],
        diff=[
            'CREATE MATERIALIZED VIEW "public"."report" AS SELECT 1 AS x WITH NO DATA',
            'COMMENT ON MATERIALIZED VIEW "public"."report" IS \'hi\'',
        ],
    )


async def test_materialized_view_over_system_view_not_refused(gen_setup: GenerateSetup) -> None:
    """
    A matview reading a system catalog view (pg_stat_activity, a common monitoring pattern)
    must not trip the matview-dependency guard: system schemas are not managed by pgmig, so
    the dependency is not a matview-on-managed-view edge that needs ordering.
    """
    body = gen_setup.select_body("pid", "pg_stat_activity", "pg_stat_activity")
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE MATERIALIZED VIEW active AS SELECT pid FROM pg_stat_activity"],
        diff=[f'CREATE MATERIALIZED VIEW "public"."active" AS {body} WITH NO DATA'],
    )


async def test_materialized_view_over_extension_view_not_refused(gen_setup: GenerateSetup) -> None:
    """
    A matview reading an extension-owned view (pg_stat_statements, in the user's own public
    schema, a common setup) must not trip the matview-dependency guard: extension-owned
    relations are not diffed, so the referenced side always exists and needs no ordering.
    Its schema is not a system schema, so only the extension-ownership leg excludes it.
    """
    body = gen_setup.select_body("userid", "pg_stat_statements", "public.pg_stat_statements")
    await gen_setup.assert_diff(
        both=["CREATE EXTENSION pg_stat_statements"],
        src=[],
        # WITH NO DATA in the fixture: querying pg_stat_statements needs the preloaded library,
        # which the test server does not have; the unpopulated matview only needs the catalog.
        dst=["CREATE MATERIALIZED VIEW stats AS SELECT userid FROM pg_stat_statements WITH NO DATA"],
        diff=[
            f'CREATE MATERIALIZED VIEW "public"."stats" AS {body} WITH NO DATA',
        ],
    )
