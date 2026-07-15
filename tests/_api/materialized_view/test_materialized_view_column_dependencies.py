from tests._api.generate_setup import GenerateSetup


def _matview_body(gen_setup: GenerateSetup, column: str, table: str, from_ref: str) -> str:
    """
    The recreated matview body as pg_get_viewdef renders it, which varies by Postgres major:
    14/15 qualify the column with the table name, 16+ do not.
    """
    match gen_setup.pg_major:
        case 14 | 15:
            rendered = f"{table}.{column}"
        case _:
            rendered = column
    return f"SELECT {rendered}\n   FROM {from_ref}"


def test_materialized_view_over_whole_row_retyped_column_is_recreated(gen_setup: GenerateSetup) -> None:
    """
    A materialized view reading a whole-row reference (SELECT t FROM t) physically stores the
    table's composite row type, so a type change to ANY column of the table blocks the ALTER
    ("cannot alter table because column m.t uses its row type"). The whole-row dependency is
    recorded as refobjsubid = 0, which expands to every column of the table, so the matview is
    dropped before the ALTER and recreated after.
    """
   await gen_setup.assert_diff(
        src=["CREATE TABLE t (id int, val integer)", "CREATE MATERIALIZED VIEW m AS SELECT t FROM t"],
        dst=["CREATE TABLE t (id int, val bigint)", "CREATE MATERIALIZED VIEW m AS SELECT t FROM t"],
        diff=[
            'DROP MATERIALIZED VIEW "public"."m"',
            'ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint',
            'CREATE MATERIALIZED VIEW "public"."m" AS SELECT t.*::public.t AS t\n   FROM public.t WITH NO DATA',
        ],
    )


def test_materialized_view_over_retyped_column_is_recreated(gen_setup: GenerateSetup) -> None:
    """
    A materialized view reading a column whose type changes is dropped before the ALTER COLUMN
    TYPE and recreated after. Postgres refuses to alter the type of a column a matview reads,
    and the type change leaves the matview definition unchanged, so only the matview-on-column
    edge drags it into the recreate set.
    """
   await gen_setup.assert_diff(
        src=["CREATE TABLE t (id int, val integer)", "CREATE MATERIALIZED VIEW m AS SELECT val FROM t"],
        dst=["CREATE TABLE t (id int, val bigint)", "CREATE MATERIALIZED VIEW m AS SELECT val FROM t"],
        diff=[
            'DROP MATERIALIZED VIEW "public"."m"',
            'ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint',
            f'CREATE MATERIALIZED VIEW "public"."m" AS {_matview_body(gen_setup, "val", "t", "public.t")} WITH NO DATA',
        ],
    )


def test_materialized_view_over_unchanged_column_not_recreated(gen_setup: GenerateSetup) -> None:
    """
    Column-level precision: a matview reading only column `keep` of a table whose other column
    `val` is retyped is left untouched. Postgres allows altering `val` while the matview reads
    only `keep`, so recreating the matview would be needless churn.
    """
   await gen_setup.assert_diff(
        src=["CREATE TABLE t (keep int, val integer)", "CREATE MATERIALIZED VIEW m AS SELECT keep FROM t"],
        dst=["CREATE TABLE t (keep int, val bigint)", "CREATE MATERIALIZED VIEW m AS SELECT keep FROM t"],
        diff=['ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint'],
    )
