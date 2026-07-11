from tests.fixtures.generate_setup import GenerateSetup


def test_table_create(gen_setup: GenerateSetup) -> None:
    """
    Table present in target but missing in source -> CREATE TABLE.
    """
    # Create the table on the target only.
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    # Verify the migration SQL creates it.
    gen_setup.assert_migration_sql('CREATE TABLE "public"."person" ("name" text);')


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


def test_table_column_ordered_by_name(gen_setup: GenerateSetup) -> None:
    """
    Table columns should be ordered by name.
    """
    # Create the table with columns not ordered by name.
    gen_setup.dst.execute("CREATE TABLE person (name text, age integer)")

    # Verify the migration SQL orders the columns by name.
    gen_setup.assert_migration_sql('CREATE TABLE "public"."person" ("age" integer, "name" text);')


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
