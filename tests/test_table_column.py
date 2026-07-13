import pytest

from pgmig import generate
from tests.fixtures.generate_setup import GenerateSetup


def test_table_column_type_widened(gen_setup: GenerateSetup) -> None:
    """
    A shared column whose type differs -> ALTER COLUMN ... TYPE. integer -> bigint is an
    implicit (assignment) cast, so no USING clause is needed and the migration converges.
    """
    gen_setup.src.execute("CREATE TABLE person (id integer)")
    gen_setup.dst.execute("CREATE TABLE person (id bigint)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ALTER COLUMN "id" TYPE bigint;')


def test_table_column_type_varchar_widened(gen_setup: GenerateSetup) -> None:
    """
    A varchar length increase renders with the canonical format_type spelling
    (character varying(N)); the wider length is an implicit cast, so it converges.
    """
    gen_setup.src.execute("CREATE TABLE person (name varchar(50))")
    gen_setup.dst.execute("CREATE TABLE person (name varchar(100))")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ALTER COLUMN "name" TYPE character varying(100);')


def test_table_column_type_unchanged_no_statement(gen_setup: GenerateSetup) -> None:
    """
    A column with the same type on both sides emits nothing.
    """
    gen_setup.execute_both("CREATE TABLE person (id integer)")

    gen_setup.assert_migration_sql("")


def test_table_column_identity_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A shared column that gains or loses an identity is unsupported; the tool must fail
    loudly instead of silently dropping the identity and reading as in sync.
    """
    gen_setup.src.execute("CREATE TABLE person (id integer)")
    gen_setup.dst.execute("CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)")

    with pytest.raises(NotImplementedError, match="identity change"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn)


def test_table_column_physical_order_preserved(gen_setup: GenerateSetup) -> None:
    """
    CREATE TABLE emits columns in the target's physical (attnum) order, not
    alphabetically. Names are deliberately out of alphabetical order so a sort-by-name
    introspection would reorder them; positional INSERT / SELECT * / pg_dump all depend
    on this order matching the target.
    """
    gen_setup.dst.execute("CREATE TABLE person (zebra text, apple text, mango text)")

    gen_setup.assert_migration_sql('CREATE TABLE "public"."person" ("zebra" text, "apple" text, "mango" text);')


def test_table_create_with_column_attributes(gen_setup: GenerateSetup) -> None:
    """
    A created table renders NOT NULL and DEFAULT inline in the column definition.
    """
    gen_setup.dst.execute("CREATE TABLE person (age integer NOT NULL DEFAULT 0)")

    gen_setup.assert_migration_sql('CREATE TABLE "public"."person" ("age" integer DEFAULT 0 NOT NULL);')


def test_table_column_added(gen_setup: GenerateSetup) -> None:
    """
    Column present in target but missing in source -> ALTER TABLE ADD COLUMN.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text, age integer)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ADD COLUMN "age" integer;')


def test_table_column_dropped(gen_setup: GenerateSetup) -> None:
    """
    Column present in source but missing in target -> ALTER TABLE DROP COLUMN.
    """
    gen_setup.src.execute("CREATE TABLE person (name text, age integer)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" DROP COLUMN "age";')


def test_table_column_added_and_dropped_ordered(gen_setup: GenerateSetup) -> None:
    """
    A table gaining one column and losing another -> both ALTERs, ordered by column name.
    """
    gen_setup.src.execute("CREATE TABLE person (name text, age integer)")
    gen_setup.dst.execute("CREATE TABLE person (name text, email text)")

    gen_setup.assert_migration_sql(
        [
            'ALTER TABLE "public"."person" DROP COLUMN "age";',
            'ALTER TABLE "public"."person" ADD COLUMN "email" text;',
        ]
    )


def test_table_column_added_with_attributes(gen_setup: GenerateSetup) -> None:
    """
    A column added to an existing table renders NOT NULL and DEFAULT inline.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text, age integer NOT NULL DEFAULT 0)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ADD COLUMN "age" integer DEFAULT 0 NOT NULL;')


def test_table_column_set_not_null(gen_setup: GenerateSetup) -> None:
    """
    Column nullable in source, NOT NULL in target -> SET NOT NULL.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text NOT NULL)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ALTER COLUMN "name" SET NOT NULL;')


def test_table_column_drop_not_null(gen_setup: GenerateSetup) -> None:
    """
    Column NOT NULL in source, nullable in target -> DROP NOT NULL.
    """
    gen_setup.src.execute("CREATE TABLE person (name text NOT NULL)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ALTER COLUMN "name" DROP NOT NULL;')


def test_table_column_drop_not_null_after_primary_key_drop(gen_setup: GenerateSetup) -> None:
    """
    A source PRIMARY KEY column (implicitly NOT NULL) becomes a plain nullable column in
    the target. The PK drop lands in the CONSTRAINT phase, so the column's DROP NOT NULL
    must be emitted after it -- Postgres refuses DROP NOT NULL while the column is still
    in a primary key ("column is in a primary key").
    """
    gen_setup.src.execute("CREATE TABLE person (id integer PRIMARY KEY)")
    gen_setup.dst.execute("CREATE TABLE person (id integer)")

    gen_setup.assert_migration_sql(
        [
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_pkey";',
            'ALTER TABLE "public"."person" ALTER COLUMN "id" DROP NOT NULL;',
        ]
    )


def test_table_column_set_default(gen_setup: GenerateSetup) -> None:
    """
    Column with no default in source, default in target -> SET DEFAULT.
    """
    gen_setup.src.execute("CREATE TABLE person (age integer)")
    gen_setup.dst.execute("CREATE TABLE person (age integer DEFAULT 0)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ALTER COLUMN "age" SET DEFAULT 0;')


def test_table_column_change_default(gen_setup: GenerateSetup) -> None:
    """
    Different default expressions -> SET DEFAULT with the target's.
    """
    gen_setup.src.execute("CREATE TABLE person (age integer DEFAULT 0)")
    gen_setup.dst.execute("CREATE TABLE person (age integer DEFAULT 1)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ALTER COLUMN "age" SET DEFAULT 1;')


def test_table_column_drop_default(gen_setup: GenerateSetup) -> None:
    """
    Default in source, none in target -> DROP DEFAULT.
    """
    gen_setup.src.execute("CREATE TABLE person (age integer DEFAULT 0)")
    gen_setup.dst.execute("CREATE TABLE person (age integer)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ALTER COLUMN "age" DROP DEFAULT;')


def test_table_column_attributes_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same type, nullability, and default on both sides -> no migration SQL.
    """
    gen_setup.execute_both("CREATE TABLE person (age integer NOT NULL DEFAULT 0)")

    gen_setup.assert_migration_sql("")
