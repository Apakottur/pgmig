from tests.fixtures.generate_setup import GenerateSetup


def test_matview_index_create(gen_setup: GenerateSetup) -> None:
    """
    Index present in target but missing in source, on a matview present on both sides
    -> CREATE INDEX.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql("CREATE INDEX report_x_idx ON public.report USING btree (x);")


def test_matview_index_on_created_matview(gen_setup: GenerateSetup) -> None:
    """
    Matview created on target with an index -> CREATE MATERIALIZED VIEW then CREATE INDEX.
    """
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql(
        [
            'CREATE MATERIALIZED VIEW "public"."report" AS SELECT 1 AS x WITH NO DATA;',
            "CREATE INDEX report_x_idx ON public.report USING btree (x);",
        ]
    )


def test_matview_index_drop(gen_setup: GenerateSetup) -> None:
    """
    Index present in source but missing in target, matview present on both -> DROP INDEX.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.src.execute("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql('DROP INDEX "public"."report_x_idx";')


def test_matview_index_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER INDEX RENAME.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.src.execute("CREATE INDEX report_x_old ON report (x)")
    gen_setup.dst.execute("CREATE INDEX report_x_new ON report (x)")

    gen_setup.assert_migration_sql('ALTER INDEX "public"."report_x_old" RENAME TO "report_x_new";')


def test_matview_index_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical matview and index on both sides -> no migration SQL.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql("")


def test_matview_index_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition (matview unchanged) -> DROP INDEX then CREATE INDEX.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x, 2 AS y")
    gen_setup.src.execute("CREATE INDEX report_idx ON report (x)")
    gen_setup.dst.execute("CREATE INDEX report_idx ON report (y)")

    gen_setup.assert_migration_sql(
        [
            'DROP INDEX "public"."report_idx";',
            "CREATE INDEX report_idx ON public.report USING btree (y);",
        ]
    )


def test_matview_index_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique index round-trips as CREATE UNIQUE INDEX (the index REFRESH CONCURRENTLY needs).
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE UNIQUE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql("CREATE UNIQUE INDEX report_x_idx ON public.report USING btree (x);")


def test_matview_index_dropped_with_matview(gen_setup: GenerateSetup) -> None:
    """
    Matview (with an index) dropped -> DROP MATERIALIZED VIEW only; the index rides along.
    """
    gen_setup.src.execute("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.src.execute("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql('DROP MATERIALIZED VIEW "public"."report";')


def test_matview_index_recreated_with_changed_matview(gen_setup: GenerateSetup) -> None:
    """
    The gap this closes: a changed matview definition drops and recreates the matview,
    which loses its indexes, so every target index must be recreated after the matview.
    """
    gen_setup.src.execute("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.src.execute("CREATE INDEX report_x_idx ON report (x)")
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW report AS SELECT 2 AS x")
    gen_setup.dst.execute("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql(
        [
            'DROP MATERIALIZED VIEW "public"."report";',
            'CREATE MATERIALIZED VIEW "public"."report" AS SELECT 2 AS x WITH NO DATA;',
            "CREATE INDEX report_x_idx ON public.report USING btree (x);",
        ]
    )


def test_matview_index_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to an index present on both sides -> COMMENT ON INDEX.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE INDEX report_x_idx ON report (x)")
    gen_setup.dst.execute("COMMENT ON INDEX report_x_idx IS 'by x'")

    gen_setup.assert_migration_sql('COMMENT ON INDEX "public"."report_x_idx" IS \'by x\';')


def test_matview_index_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment removed from an index -> COMMENT ON INDEX ... IS NULL.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.execute_both("CREATE INDEX report_x_idx ON report (x)")
    gen_setup.src.execute("COMMENT ON INDEX report_x_idx IS 'by x'")

    gen_setup.assert_migration_sql('COMMENT ON INDEX "public"."report_x_idx" IS NULL;')


def test_matview_index_create_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a created matview index carries CONCURRENTLY.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.dst.execute("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql(
        "CREATE INDEX CONCURRENTLY report_x_idx ON public.report USING btree (x);",
        index_concurrently=True,
    )


def test_matview_index_drop_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a dropped matview index carries CONCURRENTLY.
    """
    gen_setup.execute_both("CREATE MATERIALIZED VIEW report AS SELECT 1 AS x")
    gen_setup.src.execute("CREATE INDEX report_x_idx ON report (x)")

    gen_setup.assert_migration_sql(
        'DROP INDEX CONCURRENTLY "public"."report_x_idx";',
        index_concurrently=True,
    )
