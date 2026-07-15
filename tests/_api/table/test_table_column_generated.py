from tests._api.generate_setup import GenerateSetup


def test_stored_generated_column_emitted(gen_setup: GenerateSetup) -> None:
    """
    A STORED generated column is emitted with its GENERATED ALWAYS AS (...) STORED clause,
    not as a plain column defaulting to the expression (the expression lives in pg_attrdef,
    the same catalog a DEFAULT comes from, so it must be distinguished by attgenerated).
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"],
        diff=[
            'CREATE TABLE "public"."item" ("price" numeric, "qty" integer, '
            '"total" numeric GENERATED ALWAYS AS (price * (qty)::numeric) STORED)'
        ],
    )


def test_stored_generated_column_not_null_emitted(gen_setup: GenerateSetup) -> None:
    """
    A NOT NULL stored generated column keeps the NOT NULL after the STORED clause (a
    generated column may still be declared NOT NULL).
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) STORED NOT NULL)"],
        diff=[
            'CREATE TABLE "public"."item" ("b" integer, "doubled" integer GENERATED ALWAYS AS (b * 2) STORED NOT NULL)'
        ],
    )


def test_stored_generated_column_added_to_existing_table(gen_setup: GenerateSetup) -> None:
    """
    Adding a stored generated column to a table present on both sides emits ADD COLUMN with
    the GENERATED clause inline.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE item (price numeric, qty integer)"],
        dst=["CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"],
        diff=[
            'ALTER TABLE "public"."item" ADD COLUMN "total" numeric GENERATED ALWAYS AS (price * (qty)::numeric) STORED'
        ],
    )


def test_stored_generated_column_dropped(gen_setup: GenerateSetup) -> None:
    """
    Dropping a generated column is a plain DROP COLUMN.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"],
        dst=["CREATE TABLE item (price numeric, qty integer)"],
        diff=['ALTER TABLE "public"."item" DROP COLUMN "total"'],
    )


def test_stored_generated_column_type_change_omits_using(gen_setup: GenerateSetup) -> None:
    """
    A stored generated column whose own type changes (same generation expression) is altered
    with ALTER COLUMN ... TYPE and NO USING clause. Postgres refuses `USING` when altering the
    type of a generated column ("cannot specify USING when altering type of generated column"),
    so the migration must omit it, then still converge on apply.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"],
        dst=[
            "CREATE TABLE item (price numeric, qty integer, "
            "total double precision GENERATED ALWAYS AS (price * qty) STORED)"
        ],
        diff=['ALTER TABLE "public"."item" ALTER COLUMN "total" TYPE double precision'],
    )


def test_generated_ness_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A shared column that gains or loses its generated-ness is unsupported (Postgres has no
    in-place ADD GENERATED); the tool must fail loudly rather than mis-diff.
    """
    gen_setup.assert_unsupported(
        src=["CREATE TABLE item (b integer, c integer)"],
        dst=["CREATE TABLE item (b integer, c integer GENERATED ALWAYS AS (b) STORED)"],
        match="generated change",
    )


def test_generation_expression_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A stored generated column whose expression changes is unsupported (no in-place
    expression ALTER pre-PG18); it must raise rather than mis-diff.
    """
    gen_setup.assert_unsupported(
        src=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) STORED)"],
        dst=["CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 3) STORED)"],
        match="generated change",
    )
