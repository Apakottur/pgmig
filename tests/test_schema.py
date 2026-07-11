from tests.fixtures.generate_setup import GenerateSetup


def test_schema_create(gen_setup: GenerateSetup) -> None:
    """
    Schema present in target but missing in source -> CREATE SCHEMA.
    """
    new_schema_name = "banana"

    # Create the schema on the target only.
    gen_setup.dst.execute(f"CREATE SCHEMA {new_schema_name}")

    # Verify the migration SQL creates it.
    gen_setup.assert_migration_sql(f'CREATE SCHEMA "{new_schema_name}";')


def test_schema_drop(gen_setup: GenerateSetup) -> None:
    """
    Schema present in source but missing in target -> DROP SCHEMA.
    """
    new_schema_name = "banana"

    # Create the schema on the source only.
    gen_setup.src.execute(f"CREATE SCHEMA {new_schema_name}")

    # Verify the migration SQL drops it.
    gen_setup.assert_migration_sql(f'DROP SCHEMA "{new_schema_name}";')
