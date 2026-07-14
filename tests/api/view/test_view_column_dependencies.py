from tests.api.generate_setup import GenerateSetup


def _view_body(gen_setup: GenerateSetup, column: str, table: str, from_ref: str) -> str:
    """
    The recreated view body as pg_get_viewdef renders it, which varies by Postgres major:
    14/15 qualify the column with the table name, 16+ do not.
    """
    match gen_setup.pg_major:
        case 14 | 15:
            rendered = f"{table}.{column}"
        case _:
            rendered = column
    return f"SELECT {rendered}\n   FROM {from_ref}"


def test_view_over_retyped_column_is_recreated(gen_setup: GenerateSetup) -> None:
    """
    A view reading a column whose type changes is dropped before the ALTER COLUMN TYPE and
    recreated after. Postgres refuses to alter the type of a column a view reads, and the
    type change leaves the view definition unchanged, so only the view-on-column edge drags
    the view into the recreate set.
    """
    gen_setup.src.execute("CREATE TABLE t (id int, val integer)")
    gen_setup.src.execute("CREATE VIEW v AS SELECT val FROM t")
    gen_setup.dst.execute("CREATE TABLE t (id int, val bigint)")
    gen_setup.dst.execute("CREATE VIEW v AS SELECT val FROM t")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "public"."v";',
            'ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint;',
            f'CREATE VIEW "public"."v" AS {_view_body(gen_setup, "val", "t", "public.t")};',
        ]
    )


def test_view_on_view_over_retyped_column_cascades(gen_setup: GenerateSetup) -> None:
    """
    A retyped column drags in not just the view that reads it but every view that
    transitively reads that view. Neither view's definition changes, so the whole recreate
    set comes from the column edge plus the view-on-view closure.
    """
    for db in (gen_setup.src, gen_setup.dst):
        col_type = "integer" if db is gen_setup.src else "bigint"
        db.execute(f"CREATE TABLE t (val {col_type})")
        db.execute("CREATE VIEW base AS SELECT val FROM t")
        db.execute("CREATE VIEW derived AS SELECT val FROM base")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "public"."derived";',
            'DROP VIEW "public"."base";',
            'ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint;',
            f'CREATE VIEW "public"."base" AS {_view_body(gen_setup, "val", "t", "public.t")};',
            f'CREATE VIEW "public"."derived" AS {_view_body(gen_setup, "val", "base", "public.base")};',
        ]
    )


def test_view_over_unchanged_column_not_recreated(gen_setup: GenerateSetup) -> None:
    """
    Column-level precision: a view reading only column `keep` of a table whose other column
    `val` is retyped is left untouched. Postgres allows altering `val` while the view reads
    only `keep`, so recreating the view would be needless churn.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE t (keep int, val integer)", "CREATE VIEW v AS SELECT keep FROM t"],
        dst=["CREATE TABLE t (keep int, val bigint)", "CREATE VIEW v AS SELECT keep FROM t"],
        diff=['ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint'],
    )


def test_view_over_retyped_column_cross_schema(gen_setup: GenerateSetup) -> None:
    """
    The view-on-column recreate spans schemas: a view in one schema reading a retyped column
    of a table in another is dropped and recreated around the alter.
    """
    for db in (gen_setup.src, gen_setup.dst):
        col_type = "integer" if db is gen_setup.src else "bigint"
        db.execute("CREATE SCHEMA data")
        db.execute("CREATE SCHEMA api")
        db.execute(f"CREATE TABLE data.t (val {col_type})")
        db.execute("CREATE VIEW api.v AS SELECT val FROM data.t")

    gen_setup.assert_migration_sql(
        [
            'DROP VIEW "api"."v";',
            'ALTER TABLE "data"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint;',
            f'CREATE VIEW "api"."v" AS {_view_body(gen_setup, "val", "t", "data.t")};',
        ]
    )
