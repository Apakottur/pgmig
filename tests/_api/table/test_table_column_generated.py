import pytest

from tests._api.generate_setup import GenerateSetup


async def test_stored_generated_column_emitted(gen_setup: GenerateSetup) -> None:
    """
    A STORED generated column is emitted with its GENERATED ALWAYS AS (...) STORED clause,
    not as a plain column defaulting to the expression (the expression lives in pg_attrdef,
    the same catalog a DEFAULT comes from, so it must be distinguished by attgenerated).
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"],
        diff=[
            'CREATE TABLE "public"."item" ("price" numeric, "qty" integer, '
            '"total" numeric GENERATED ALWAYS AS (price * (qty)::numeric) STORED)'
        ],
    )


async def test_stored_generated_column_not_null_emitted(gen_setup: GenerateSetup) -> None:
    """
    A NOT NULL stored generated column keeps the NOT NULL after the STORED clause (a
    generated column may still be declared NOT NULL).
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) STORED NOT NULL)"],
        diff=[
            'CREATE TABLE "public"."item" ("b" integer, "doubled" integer GENERATED ALWAYS AS (b * 2) STORED NOT NULL)'
        ],
    )


async def test_stored_generated_column_added_to_existing_table(gen_setup: GenerateSetup) -> None:
    """
    Adding a stored generated column to a table present on both sides emits ADD COLUMN with
    the GENERATED clause inline.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE item (price numeric, qty integer)"],
        dst=["CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"],
        diff=[
            'ALTER TABLE "public"."item" ADD COLUMN "total" numeric GENERATED ALWAYS AS (price * (qty)::numeric) STORED'
        ],
    )


async def test_stored_generated_column_dropped(gen_setup: GenerateSetup) -> None:
    """
    Dropping a generated column is a plain DROP COLUMN.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"],
        dst=["CREATE TABLE item (price numeric, qty integer)"],
        diff=['ALTER TABLE "public"."item" DROP COLUMN "total"'],
    )


async def test_stored_generated_column_type_change_omits_using(gen_setup: GenerateSetup) -> None:
    """
    A stored generated column whose own type changes (same generation expression) is altered
    with ALTER COLUMN ... TYPE and NO USING clause. Postgres refuses `USING` when altering the
    type of a generated column ("cannot specify USING when altering type of generated column"),
    so the migration must omit it, then still converge on apply.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"],
        dst=[
            "CREATE TABLE item (price numeric, qty integer, "
            "total double precision GENERATED ALWAYS AS (price * qty) STORED)"
        ],
        diff=['ALTER TABLE "public"."item" ALTER COLUMN "total" TYPE double precision'],
    )


async def test_generated_ness_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A shared column that gains or loses its generated-ness is unsupported (Postgres has no
    in-place ADD GENERATED); the tool must fail loudly rather than mis-diff.
    """
    await gen_setup.assert_unsupported(
        src=["CREATE TABLE item (b integer, c integer)"],
        dst=["CREATE TABLE item (b integer, c integer GENERATED ALWAYS AS (b) STORED)"],
        match="generated change",
    )


async def test_stored_generation_expression_change_drops_and_readds(gen_setup: GenerateSetup) -> None:
    """
    A stored generated column whose expression changes is rebuilt with DROP COLUMN + ADD COLUMN.
    A stored column's data is derived, so the drop+add recomputes it non-destructively, and this
    is portable to pre-PG18 (which has no in-place expression ALTER).
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) STORED)"],
        dst=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 3) STORED)"],
        diff=[
            'ALTER TABLE "public"."item" DROP COLUMN "doubled"',
            'ALTER TABLE "public"."item" ADD COLUMN "doubled" integer GENERATED ALWAYS AS (b * 3) STORED',
        ],
    )


async def test_virtual_generated_column_emitted(gen_setup: GenerateSetup) -> None:
    """
    A virtual generated column (PG18+) is emitted with its GENERATED ALWAYS AS (...) VIRTUAL
    clause.
    """
    if gen_setup.pg_major < 18:
        pytest.skip("virtual generated columns require Postgres 18+")
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) VIRTUAL)"],
        diff=['CREATE TABLE "public"."item" ("b" integer, "doubled" integer GENERATED ALWAYS AS (b * 2) VIRTUAL)'],
    )


async def test_virtual_generated_column_added_to_existing_table(gen_setup: GenerateSetup) -> None:
    """
    Adding a virtual generated column to a table present on both sides emits ADD COLUMN with the
    VIRTUAL clause inline.
    """
    if gen_setup.pg_major < 18:
        pytest.skip("virtual generated columns require Postgres 18+")
    await gen_setup.assert_diff(
        src=["CREATE TABLE item (b integer)"],
        dst=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) VIRTUAL)"],
        diff=['ALTER TABLE "public"."item" ADD COLUMN "doubled" integer GENERATED ALWAYS AS (b * 2) VIRTUAL'],
    )


async def test_virtual_generated_column_dropped(gen_setup: GenerateSetup) -> None:
    """
    Dropping a virtual generated column is a plain DROP COLUMN.
    """
    if gen_setup.pg_major < 18:
        pytest.skip("virtual generated columns require Postgres 18+")
    await gen_setup.assert_diff(
        src=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) VIRTUAL)"],
        dst=["CREATE TABLE item (b integer)"],
        diff=['ALTER TABLE "public"."item" DROP COLUMN "doubled"'],
    )


async def test_virtual_generation_expression_change_sets_expression(gen_setup: GenerateSetup) -> None:
    """
    A virtual generated column's expression changes in place via SET EXPRESSION AS (...) (PG18);
    it has no stored data to rebuild, so no DROP/ADD is needed.
    """
    if gen_setup.pg_major < 18:
        pytest.skip("virtual generated columns require Postgres 18+")
    await gen_setup.assert_diff(
        src=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) VIRTUAL)"],
        dst=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 5) VIRTUAL)"],
        diff=['ALTER TABLE "public"."item" ALTER COLUMN "doubled" SET EXPRESSION AS (b * 5)'],
    )
