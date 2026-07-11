from tests.fixtures.generate_setup import GenerateSetup


def test_schema_create(gen_setup: GenerateSetup) -> None:
    """
    Schema present in target but missing in source -> CREATE SCHEMA.
    """
    # Create the schema on the target only.
    gen_setup.dst.execute("CREATE SCHEMA reporting")

    # Verify the migration SQL creates it.
    gen_setup.assert_migration_sql('CREATE SCHEMA "reporting";')


def test_schema_drop(gen_setup: GenerateSetup) -> None:
    """
    Schema present in source but missing in target -> DROP SCHEMA.
    """
    # Create the schema on the source only.
    gen_setup.src.execute("CREATE SCHEMA reporting")

    # Verify the migration SQL drops it.
    gen_setup.assert_migration_sql('DROP SCHEMA "reporting";')
