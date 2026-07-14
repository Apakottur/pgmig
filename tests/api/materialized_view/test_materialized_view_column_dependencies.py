from tests.api.generate_setup import GenerateSetup


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


def test_materialized_view_over_retyped_column_is_recreated(gen_setup: GenerateSetup) -> None:
    """
    A materialized view reading a column whose type changes is dropped before the ALTER COLUMN
    TYPE and recreated after. Postgres refuses to alter the type of a column a matview reads,
    and the type change leaves the matview definition unchanged, so only the matview-on-column
    edge drags it into the recreate set.
    """
    gen_setup.assert_diff(
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
    gen_setup.assert_diff(
        src=["CREATE TABLE t (keep int, val integer)", "CREATE MATERIALIZED VIEW m AS SELECT keep FROM t"],
        dst=["CREATE TABLE t (keep int, val bigint)", "CREATE MATERIALIZED VIEW m AS SELECT keep FROM t"],
        diff=['ALTER TABLE "public"."t" ALTER COLUMN "val" TYPE bigint USING "val"::bigint'],
    )
