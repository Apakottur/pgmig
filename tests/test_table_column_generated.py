import pytest

from pgmig import generate
from pgmig._diff.tables import _column_def, _parenthesize_generation
from pgmig._models import Column
from tests.fixtures.generate_setup import GenerateSetup


def test_stored_generated_column_emitted(gen_setup: GenerateSetup) -> None:
    """
    A STORED generated column is emitted with its GENERATED ALWAYS AS (...) STORED clause,
    not as a plain column defaulting to the expression (the expression lives in pg_attrdef,
    the same catalog a DEFAULT comes from, so it must be distinguished by attgenerated).
    """
    gen_setup.dst.execute(
        "CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"
    )

    gen_setup.assert_migration_sql(
        'CREATE TABLE "public"."item" ("price" numeric, "qty" integer, '
        '"total" numeric GENERATED ALWAYS AS (price * (qty)::numeric) STORED);'
    )


def test_stored_generated_column_not_null_emitted(gen_setup: GenerateSetup) -> None:
    """
    A NOT NULL stored generated column keeps the NOT NULL after the STORED clause (a
    generated column may still be declared NOT NULL).
    """
    gen_setup.dst.execute("CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) STORED NOT NULL)")

    gen_setup.assert_migration_sql(
        'CREATE TABLE "public"."item" ("b" integer, "doubled" integer GENERATED ALWAYS AS (b * 2) STORED NOT NULL);'
    )


def test_stored_generated_column_added_to_existing_table(gen_setup: GenerateSetup) -> None:
    """
    Adding a stored generated column to a table present on both sides emits ADD COLUMN with
    the GENERATED clause inline.
    """
    gen_setup.src.execute("CREATE TABLE item (price numeric, qty integer)")
    gen_setup.dst.execute(
        "CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"
    )

    gen_setup.assert_migration_sql(
        'ALTER TABLE "public"."item" ADD COLUMN "total" numeric GENERATED ALWAYS AS (price * (qty)::numeric) STORED;'
    )


def test_stored_generated_column_dropped(gen_setup: GenerateSetup) -> None:
    """
    Dropping a generated column is a plain DROP COLUMN.
    """
    gen_setup.src.execute(
        "CREATE TABLE item (price numeric, qty integer, total numeric GENERATED ALWAYS AS (price * qty) STORED)"
    )
    gen_setup.dst.execute("CREATE TABLE item (price numeric, qty integer)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."item" DROP COLUMN "total";')


def test_generated_ness_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A shared column that gains or loses its generated-ness is unsupported (Postgres has no
    in-place ADD GENERATED); the tool must fail loudly rather than mis-diff.
    """
    gen_setup.src.execute("CREATE TABLE item (b integer, c integer)")
    gen_setup.dst.execute("CREATE TABLE item (b integer, c integer GENERATED ALWAYS AS (b) STORED)")

    with pytest.raises(NotImplementedError, match="generated change"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)


def test_generation_expression_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A stored generated column whose expression changes is unsupported (no in-place
    expression ALTER pre-PG18); it must raise rather than mis-diff.
    """
    gen_setup.src.execute("CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 2) STORED)")
    gen_setup.dst.execute("CREATE TABLE item (b integer, doubled integer GENERATED ALWAYS AS (b * 3) STORED)")

    with pytest.raises(NotImplementedError, match="generated change"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)


def test_virtual_generated_column_raises() -> None:
    """
    Virtual generated columns (PG18+, attgenerated 'v') are unsupported. Unit-tested on
    _column_def directly since a live virtual column only exists on PG18.
    """
    column = Column(
        name="v",
        type="integer",
        not_null=False,
        default=None,
        comment=None,
        identity="",
        serial_sequence=None,
        generated="v",
        generation_expression="(b * 2)",
    )

    with pytest.raises(NotImplementedError, match="Virtual generated column"):
        _column_def(column)


def test_parenthesize_generation_normalizes_to_one_pair() -> None:
    """
    The generation expression is wrapped in exactly one outer paren pair: an already-wrapping
    pair is stripped first, a bare/function expression is wrapped as-is, and a leading paren
    that does not span the whole expression is left in place.
    """
    assert _parenthesize_generation("(a * b)") == "(a * b)"  # already wrapped -> unchanged
    assert _parenthesize_generation("upper(x)") == "(upper(x))"  # function call -> wrapped
    assert _parenthesize_generation("b") == "(b)"  # bare column -> wrapped
    assert _parenthesize_generation("(a) + (b)") == "((a) + (b))"  # partial leading paren -> wrapped whole
