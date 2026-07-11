from tests.fixtures.generate_setup import GenerateSetup


def test_table_create_with_comment(gen_setup: GenerateSetup) -> None:
    """
    Table created on target with a comment -> CREATE TABLE then COMMENT ON TABLE.
    """
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON TABLE person IS 'people'")

    gen_setup.assert_migration_sql(
        'CREATE TABLE "public"."person" ("name" text);\nCOMMENT ON TABLE "public"."person" IS \'people\';'
    )


def test_table_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical table both sides, comment only on target -> COMMENT ON TABLE.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON TABLE person IS 'people'")

    gen_setup.assert_migration_sql('COMMENT ON TABLE "public"."person" IS \'people\';')


def test_table_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Same table both sides with differing comments -> COMMENT ON TABLE with target's.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("COMMENT ON TABLE person IS 'old'")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON TABLE person IS 'new'")

    gen_setup.assert_migration_sql('COMMENT ON TABLE "public"."person" IS \'new\';')


def test_table_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source but none on target -> COMMENT ON TABLE ... IS NULL.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("COMMENT ON TABLE person IS 'people'")
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    gen_setup.assert_migration_sql('COMMENT ON TABLE "public"."person" IS NULL;')


def test_table_comment_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same table and same comment on both sides -> no migration SQL.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("COMMENT ON TABLE person IS 'people'")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON TABLE person IS 'people'")

    gen_setup.assert_migration_sql("")


def test_table_comment_with_single_quote(gen_setup: GenerateSetup) -> None:
    """
    Comment containing a single quote is escaped by doubling.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON TABLE person IS 'it''s people'")

    gen_setup.assert_migration_sql("COMMENT ON TABLE \"public\".\"person\" IS 'it''s people';")
