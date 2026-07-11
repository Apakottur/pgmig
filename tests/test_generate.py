from tests.fixtures.generate_setup import GenerateSetup


def test_generate_sanity(gen_setup: GenerateSetup) -> None:
    """
    Sanity test - no SQL is run on either DB so no migration SQL is generated.
    """
    # Run harmless SQL.
    result = gen_setup.src.execute("SELECT 1")
    assert result == [(1,)]
    result = gen_setup.dst.execute("SELECT 1")
    assert result == [(1,)]

    # Verify migration SQL is empty.
    gen_setup.assert_migration_sql("")


def test_extension_create(gen_setup: GenerateSetup) -> None:
    """
    Extension present in target but missing in source -> CREATE EXTENSION.
    """
    # Install the extension on the target only.
    gen_setup.dst.install_extension("pg_trgm")
    version, schema = gen_setup.dst.extension_info("pg_trgm")

    # Verify the migration SQL creates it with the target's exact version and schema.
    gen_setup.assert_migration_sql(f'CREATE EXTENSION "pg_trgm" VERSION \'{version}\' SCHEMA "{schema}";')


def test_extension_drop(gen_setup: GenerateSetup) -> None:
    """
    Extension present in source but missing in target -> DROP EXTENSION.
    """
    # Install the extension on the source only.
    gen_setup.src.install_extension("pg_trgm")

    # Verify the migration SQL drops it.
    gen_setup.assert_migration_sql('DROP EXTENSION "pg_trgm";')


def test_extension_version_update(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but with different versions -> ALTER EXTENSION UPDATE.
    """
    # Pick an extension exposing multiple versions.
    name, old_version, new_version = gen_setup.src.pick_multi_version_extension()

    # Install the old version on the source and the new version on the target.
    gen_setup.src.install_extension(name, version=old_version)
    gen_setup.dst.install_extension(name, version=new_version)

    # Verify the migration SQL updates to the target version.
    gen_setup.assert_migration_sql(f"ALTER EXTENSION \"{name}\" UPDATE TO '{new_version}';")


def test_extension_set_schema(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but in different schemas -> ALTER EXTENSION SET SCHEMA.
    """
    # Install a relocatable extension into different schemas on each side.
    gen_setup.src.install_extension("hstore")
    gen_setup.dst.execute("CREATE SCHEMA other")
    gen_setup.dst.install_extension("hstore", schema="other")

    # Verify the migration SQL relocates it to the target schema.
    gen_setup.assert_migration_sql('ALTER EXTENSION "hstore" SET SCHEMA "other";')
