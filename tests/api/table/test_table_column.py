from tests.api.generate_setup import GenerateSetup


def test_table_column_type_widened(gen_setup: GenerateSetup) -> None:
    """
    A shared column whose type differs -> ALTER COLUMN ... TYPE ... USING col::newtype.
    The explicit cast is a superset of the implicit (assignment) integer -> bigint cast,
    so the migration still converges.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer)"],
        dst=["CREATE TABLE person (id bigint)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" TYPE bigint USING "id"::bigint'],
    )


def test_table_column_type_varchar_widened(gen_setup: GenerateSetup) -> None:
    """
    A varchar length increase renders with the canonical format_type spelling
    (character varying(N)), carried through the USING cast expression too.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (name varchar(50))"],
        dst=["CREATE TABLE person (name varchar(100))"],
        diff=[
            'ALTER TABLE "public"."person" ALTER COLUMN "name" '
            'TYPE character varying(100) USING "name"::character varying(100)'
        ],
    )


def test_table_column_type_text_to_integer(gen_setup: GenerateSetup) -> None:
    """
    Text -> integer needs an explicit cast; USING col::integer makes it converge (the
    common manual-migration chore this feature unlocks).
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (id text)"],
        dst=["CREATE TABLE person (id integer)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "id" TYPE integer USING "id"::integer'],
    )


def test_table_column_type_varchar_to_enum(gen_setup: GenerateSetup) -> None:
    """
    Varchar -> enum casts via USING col::enumtype; the enum type is fully qualified by the
    empty-search_path introspection.
    """
    gen_setup.execute_both("CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')")
    gen_setup.src.execute("CREATE TABLE person (m varchar)")
    gen_setup.dst.execute("CREATE TABLE person (m mood)")

    gen_setup.assert_migration_sql(
        'ALTER TABLE "public"."person" ALTER COLUMN "m" TYPE public.mood USING "m"::public.mood;'
    )


def test_table_column_type_timestamp_to_timestamptz(gen_setup: GenerateSetup) -> None:
    """
    Timestamp -> timestamptz (a common timezone migration) casts via USING col::newtype.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE event (ts timestamp)"],
        dst=["CREATE TABLE event (ts timestamptz)"],
        diff=[
            'ALTER TABLE "public"."event" ALTER COLUMN "ts" '
            'TYPE timestamp with time zone USING "ts"::timestamp with time zone'
        ],
    )


def test_table_column_type_unchanged_no_statement(gen_setup: GenerateSetup) -> None:
    """
    A column with the same type on both sides emits nothing.
    """
    gen_setup.execute_both("CREATE TABLE person (id integer)")

    gen_setup.assert_migration_sql("")


def test_table_column_physical_order_preserved(gen_setup: GenerateSetup) -> None:
    """
    CREATE TABLE emits columns in the target's physical (attnum) order, not
    alphabetically. Names are deliberately out of alphabetical order so a sort-by-name
    introspection would reorder them; positional INSERT / SELECT * / pg_dump all depend
    on this order matching the target.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE person (zebra text, apple text, mango text)"],
        diff=['CREATE TABLE "public"."person" ("zebra" text, "apple" text, "mango" text)'],
    )


def test_table_create_with_column_attributes(gen_setup: GenerateSetup) -> None:
    """
    A created table renders NOT NULL and DEFAULT inline in the column definition.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE person (age integer NOT NULL DEFAULT 0)"],
        diff=['CREATE TABLE "public"."person" ("age" integer DEFAULT 0 NOT NULL)'],
    )


def test_table_column_added(gen_setup: GenerateSetup) -> None:
    """
    Column present in target but missing in source -> ALTER TABLE ADD COLUMN.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text, age integer)"],
        diff=['ALTER TABLE "public"."person" ADD COLUMN "age" integer'],
    )


def test_table_column_dropped(gen_setup: GenerateSetup) -> None:
    """
    Column present in source but missing in target -> ALTER TABLE DROP COLUMN.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (name text, age integer)"],
        dst=["CREATE TABLE person (name text)"],
        diff=['ALTER TABLE "public"."person" DROP COLUMN "age"'],
    )


def test_table_column_added_and_dropped_ordered(gen_setup: GenerateSetup) -> None:
    """
    A table gaining one column and losing another -> both ALTERs, ordered by column name.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (name text, age integer)"],
        dst=["CREATE TABLE person (name text, email text)"],
        diff=[
            'ALTER TABLE "public"."person" DROP COLUMN "age"',
            'ALTER TABLE "public"."person" ADD COLUMN "email" text',
        ],
    )


def test_table_column_added_with_attributes(gen_setup: GenerateSetup) -> None:
    """
    A column added to an existing table renders NOT NULL and DEFAULT inline.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text, age integer NOT NULL DEFAULT 0)"],
        diff=['ALTER TABLE "public"."person" ADD COLUMN "age" integer DEFAULT 0 NOT NULL'],
    )


def test_table_column_set_not_null(gen_setup: GenerateSetup) -> None:
    """
    Column nullable in source, NOT NULL in target -> SET NOT NULL.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text NOT NULL)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "name" SET NOT NULL'],
    )


def test_table_column_drop_not_null(gen_setup: GenerateSetup) -> None:
    """
    Column NOT NULL in source, nullable in target -> DROP NOT NULL.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (name text NOT NULL)"],
        dst=["CREATE TABLE person (name text)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "name" DROP NOT NULL'],
    )


def test_table_column_drop_not_null_after_primary_key_drop(gen_setup: GenerateSetup) -> None:
    """
    A source PRIMARY KEY column (implicitly NOT NULL) becomes a plain nullable column in
    the target. The PK drop lands in the CONSTRAINT phase, so the column's DROP NOT NULL
    must be emitted after it -- Postgres refuses DROP NOT NULL while the column is still
    in a primary key ("column is in a primary key").
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer PRIMARY KEY)"],
        dst=["CREATE TABLE person (id integer)"],
        diff=[
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_pkey"',
            'ALTER TABLE "public"."person" ALTER COLUMN "id" DROP NOT NULL',
        ],
    )


def test_table_column_set_default(gen_setup: GenerateSetup) -> None:
    """
    Column with no default in source, default in target -> SET DEFAULT.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (age integer)"],
        dst=["CREATE TABLE person (age integer DEFAULT 0)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "age" SET DEFAULT 0'],
    )


def test_table_column_change_default(gen_setup: GenerateSetup) -> None:
    """
    Different default expressions -> SET DEFAULT with the target's.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (age integer DEFAULT 0)"],
        dst=["CREATE TABLE person (age integer DEFAULT 1)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "age" SET DEFAULT 1'],
    )


def test_table_column_drop_default(gen_setup: GenerateSetup) -> None:
    """
    Default in source, none in target -> DROP DEFAULT.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (age integer DEFAULT 0)"],
        dst=["CREATE TABLE person (age integer)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "age" DROP DEFAULT'],
    )


def test_table_column_attributes_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same type, nullability, and default on both sides -> no migration SQL.
    """
    gen_setup.execute_both("CREATE TABLE person (age integer NOT NULL DEFAULT 0)")

    gen_setup.assert_migration_sql("")
