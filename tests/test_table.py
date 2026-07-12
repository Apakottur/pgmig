from tests.fixtures.generate_setup import GenerateSetup


def test_table_create(gen_setup: GenerateSetup) -> None:
    """
    Table present in target but missing in source -> CREATE TABLE.
    """
    # Create the table on the target only.
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    # Verify the migration SQL creates it.
    gen_setup.assert_migration_sql('CREATE TABLE "public"."person" ("name" text);')


def test_table_create_with_quote_in_name(gen_setup: GenerateSetup) -> None:
    """
    A table (and column) whose name contains a double quote is quoted correctly:
    the embedded quote is doubled, so the emitted DDL is valid and converges.
    """
    gen_setup.dst.execute('CREATE TABLE "we""ird" ("c""ol" text)')

    gen_setup.assert_migration_sql('CREATE TABLE "public"."we""ird" ("c""ol" text);')


def test_table_drop(gen_setup: GenerateSetup) -> None:
    """
    Table present in source but missing in target -> DROP TABLE.
    """
    # Create the table on the source only.
    gen_setup.src.execute("CREATE TABLE person (name text)")

    # Verify the migration SQL drops it.
    gen_setup.assert_migration_sql('DROP TABLE "public"."person";')


def test_table_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical table on both sides -> no migration SQL.
    """
    # Create the same table on both sides.
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    # Verify no migration SQL is generated.
    gen_setup.assert_migration_sql("")
