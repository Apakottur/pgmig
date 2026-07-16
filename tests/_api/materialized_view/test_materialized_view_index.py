from tests._api.generate_setup import GenerateSetup


async def test_matview_index_create(gen_setup: GenerateSetup) -> None:
    """
    Index present in target but missing in source, on a matview present on both sides
    -> CREATE INDEX.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        src=[],
        dst=["CREATE INDEX report_x_idx ON report (x)"],
        diff=["CREATE INDEX report_x_idx ON public.report USING btree (x)"],
    )


async def test_matview_index_on_created_matview(gen_setup: GenerateSetup) -> None:
    """
    Matview created on target with an index -> CREATE MATERIALIZED VIEW then CREATE INDEX.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x", "CREATE INDEX report_x_idx ON report (x)"],
        diff=[
            'CREATE MATERIALIZED VIEW "public"."report" AS SELECT 1 AS x WITH NO DATA',
            "CREATE INDEX report_x_idx ON public.report USING btree (x)",
        ],
    )


async def test_matview_index_drop(gen_setup: GenerateSetup) -> None:
    """
    Index present in source but missing in target, matview present on both -> DROP INDEX.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        src=["CREATE INDEX report_x_idx ON report (x)"],
        dst=[],
        diff=['DROP INDEX "public"."report_x_idx"'],
    )


async def test_matview_index_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER INDEX RENAME.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        src=["CREATE INDEX report_x_old ON report (x)"],
        dst=["CREATE INDEX report_x_new ON report (x)"],
        diff=['ALTER INDEX "public"."report_x_old" RENAME TO "report_x_new"'],
    )


async def test_matview_index_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical matview and index on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x", "CREATE INDEX report_x_idx ON report (x)"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_matview_index_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition (matview unchanged) -> DROP INDEX then CREATE INDEX.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x, 2 AS y"],
        src=["CREATE INDEX report_idx ON report (x)"],
        dst=["CREATE INDEX report_idx ON report (y)"],
        diff=[
            'DROP INDEX "public"."report_idx"',
            "CREATE INDEX report_idx ON public.report USING btree (y)",
        ],
    )


async def test_matview_index_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique index round-trips as CREATE UNIQUE INDEX (the index REFRESH CONCURRENTLY needs).
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        src=[],
        dst=["CREATE UNIQUE INDEX report_x_idx ON report (x)"],
        diff=["CREATE UNIQUE INDEX report_x_idx ON public.report USING btree (x)"],
    )


async def test_matview_index_dropped_with_matview(gen_setup: GenerateSetup) -> None:
    """
    Matview (with an index) dropped -> DROP MATERIALIZED VIEW only; the index rides along.
    """
    await gen_setup.assert_diff(
        src=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x", "CREATE INDEX report_x_idx ON report (x)"],
        dst=[],
        diff=['DROP MATERIALIZED VIEW "public"."report"'],
    )


async def test_matview_index_recreated_with_changed_matview(gen_setup: GenerateSetup) -> None:
    """
    The gap this closes: a changed matview definition drops and recreates the matview,
    which loses its indexes, so every target index must be recreated after the matview.
    """
    await gen_setup.assert_diff(
        src=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x", "CREATE INDEX report_x_idx ON report (x)"],
        dst=["CREATE MATERIALIZED VIEW report AS SELECT 2 AS x", "CREATE INDEX report_x_idx ON report (x)"],
        diff=[
            'DROP MATERIALIZED VIEW "public"."report"',
            'CREATE MATERIALIZED VIEW "public"."report" AS SELECT 2 AS x WITH NO DATA',
            "CREATE INDEX report_x_idx ON public.report USING btree (x)",
        ],
    )


async def test_matview_index_recreated_over_retyped_column(gen_setup: GenerateSetup) -> None:
    """
    The bug this closes: a matview reading a column whose type changes is dropped and
    recreated even though its definition is unchanged (only the matview-on-column edge
    catches it), which loses its indexes -- including the unique index REFRESH CONCURRENTLY
    needs. The index differ must treat this matview as recreated and create every index fresh.
    """
    # pg_get_viewdef qualifies the column with the table on PG14/15 but not 16+.
    body = "SELECT t.val\n   FROM public.t" if gen_setup.pg_major in (14, 15) else "SELECT val\n   FROM public.t"
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE t (id int, val integer)",
            "CREATE MATERIALIZED VIEW m AS SELECT val FROM t",
            "CREATE UNIQUE INDEX m_val ON m (val)",
        ],
        dst=[
            "CREATE TABLE t (id int, val bigint)",
            "CREATE MATERIALIZED VIEW m AS SELECT val FROM t",
            "CREATE UNIQUE INDEX m_val ON m (val)",
        ],
        diff=[
            'DROP MATERIALIZED VIEW "public"."m"',
            'ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint',
            f'CREATE MATERIALIZED VIEW "public"."m" AS {body} WITH NO DATA',
            "CREATE UNIQUE INDEX m_val ON public.m USING btree (val)",
        ],
    )


async def test_matview_index_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to an index present on both sides -> COMMENT ON INDEX.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x", "CREATE INDEX report_x_idx ON report (x)"],
        src=[],
        dst=["COMMENT ON INDEX report_x_idx IS 'by x'"],
        diff=['COMMENT ON INDEX "public"."report_x_idx" IS \'by x\''],
    )


async def test_matview_index_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment removed from an index -> COMMENT ON INDEX ... IS NULL.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x", "CREATE INDEX report_x_idx ON report (x)"],
        src=["COMMENT ON INDEX report_x_idx IS 'by x'"],
        dst=[],
        diff=['COMMENT ON INDEX "public"."report_x_idx" IS NULL'],
    )


async def test_matview_index_create_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a created matview index carries CONCURRENTLY.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        src=[],
        dst=["CREATE INDEX report_x_idx ON report (x)"],
        diff=["CREATE INDEX CONCURRENTLY report_x_idx ON public.report USING btree (x)"],
        index_concurrently=True,
    )


async def test_matview_index_drop_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a dropped matview index carries CONCURRENTLY.
    """
    await gen_setup.assert_diff(
        both=["CREATE MATERIALIZED VIEW report AS SELECT 1 AS x"],
        src=["CREATE INDEX report_x_idx ON report (x)"],
        dst=[],
        diff=['DROP INDEX CONCURRENTLY "public"."report_x_idx"'],
        index_concurrently=True,
    )
