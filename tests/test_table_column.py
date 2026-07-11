from tests.fixtures.generate_setup import GenerateSetup


def test_table_column_ordered_by_name(gen_setup: GenerateSetup) -> None:
    """
    Table columns should be ordered by name.
    """
    # Create the table with columns not ordered by name.
    gen_setup.dst.execute("CREATE TABLE person (name text, age integer)")

    # Verify the migration SQL orders the columns by name.
    gen_setup.assert_migration_sql('CREATE TABLE "public"."person" ("age" integer, "name" text);')


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


def test_table_column_type_change_ignored(gen_setup: GenerateSetup) -> None:
    """
    Same column name with a different type -> no migration SQL (type changes are out of scope).
    """
    gen_setup.src.execute("CREATE TABLE person (age text)")
    gen_setup.dst.execute("CREATE TABLE person (age integer)")

    gen_setup.assert_migration_sql("")


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
    gen_setup.src.execute("CREATE TABLE person (age integer NOT NULL DEFAULT 0)")
    gen_setup.dst.execute("CREATE TABLE person (age integer NOT NULL DEFAULT 0)")

    gen_setup.assert_migration_sql("")


def test_table_column_create_with_comment(gen_setup: GenerateSetup) -> None:
    """
    A created table with a commented column -> CREATE TABLE then COMMENT ON COLUMN.
    """
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON COLUMN person.name IS 'full name'")

    gen_setup.assert_migration_sql(
        [
            'CREATE TABLE "public"."person" ("name" text);',
            'COMMENT ON COLUMN "public"."person"."name" IS \'full name\';',
        ]
    )


def test_table_column_add_with_comment(gen_setup: GenerateSetup) -> None:
    """
    A column added to an existing table with a comment -> ADD COLUMN then COMMENT ON COLUMN.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text, age integer)")
    gen_setup.dst.execute("COMMENT ON COLUMN person.age IS 'years'")

    gen_setup.assert_migration_sql(
        [
            'ALTER TABLE "public"."person" ADD COLUMN "age" integer;',
            'COMMENT ON COLUMN "public"."person"."age" IS \'years\';',
        ]
    )


def test_table_column_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical column both sides, comment only on target -> COMMENT ON COLUMN.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON COLUMN person.name IS 'full name'")

    gen_setup.assert_migration_sql('COMMENT ON COLUMN "public"."person"."name" IS \'full name\';')


def test_table_column_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Different column comments -> COMMENT ON COLUMN with the target's.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("COMMENT ON COLUMN person.name IS 'old'")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON COLUMN person.name IS 'new'")

    gen_setup.assert_migration_sql('COMMENT ON COLUMN "public"."person"."name" IS \'new\';')


def test_table_column_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source but none on target -> COMMENT ON COLUMN ... IS NULL.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("COMMENT ON COLUMN person.name IS 'full name'")
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    gen_setup.assert_migration_sql('COMMENT ON COLUMN "public"."person"."name" IS NULL;')


def test_table_column_comment_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same column comment on both sides -> no migration SQL.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("COMMENT ON COLUMN person.name IS 'full name'")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON COLUMN person.name IS 'full name'")

    gen_setup.assert_migration_sql("")


def test_table_column_comment_with_single_quote(gen_setup: GenerateSetup) -> None:
    """
    Column comment containing a single quote is escaped by doubling.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON COLUMN person.name IS 'it''s a name'")

    gen_setup.assert_migration_sql('COMMENT ON COLUMN "public"."person"."name" IS \'it\'\'s a name\';')
