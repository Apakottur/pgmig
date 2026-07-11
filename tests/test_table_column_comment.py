from tests.fixtures.generate_setup import GenerateSetup


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
