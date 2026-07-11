import psycopg
from psycopg import sql

from tests.fixtures.generate_setup import GenerateSetup
from tests.utils.db_utils import DbConnection


def _version_key(version: str) -> tuple[int, ...]:
    """
    Sort key for Postgres extension versions (e.g. '1.10' sorts after '1.4').
    """
    return tuple(int(part) for part in version.split("."))


def _create_extension(conn: DbConnection, name: str, *, version: str | None = None, schema: str | None = None) -> None:
    """
    Install an extension, optionally pinning its version and/or schema.
    """
    stmt = sql.SQL("CREATE EXTENSION {name}").format(name=sql.Identifier(name))
    if version is not None:
        stmt += sql.SQL(" VERSION {version}").format(version=sql.Literal(version))
    if schema is not None:
        stmt += sql.SQL(" SCHEMA {schema}").format(schema=sql.Identifier(schema))

    with psycopg.connect(conn.dsn, autocommit=True) as pg_conn:
        pg_conn.execute(stmt)


def _pick_multi_version_extension(conn: DbConnection) -> tuple[str, str, str]:
    """
    Find an extension exposing more than one installable version.

    Returns (name, min_version, max_version), choosing the first extension by
    name so the selection is deterministic across runs.
    """
    rows = conn.execute("SELECT name, version FROM pg_available_extension_versions ORDER BY name")
    versions_by_name: dict[str, list[str]] = {}
    for name, version in rows:
        versions_by_name.setdefault(name, []).append(version)

    for name in sorted(versions_by_name):
        versions = sorted(versions_by_name[name], key=_version_key)
        if len(versions) > 1:
            return name, versions[0], versions[-1]

    raise AssertionError("no extension with multiple versions available")


def _extension_info(conn: DbConnection, name: str) -> tuple[str, str]:
    """
    Return the installed (version, schema) of the given extension.
    """
    result = conn.execute(
        "SELECT e.extversion, n.nspname "
        "FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace "
        "WHERE e.extname = %s",
        (name,),
    )
    assert len(result) == 1, f"extension {name!r} not installed"
    version, schema = result[0]
    return version, schema


def test_extension_create(gen_setup: GenerateSetup) -> None:
    """
    Extension present in target but missing in source -> CREATE EXTENSION.
    """
    # Install the extension on the target only.
    _create_extension(gen_setup.dst, "pg_trgm")
    version, schema = _extension_info(gen_setup.dst, "pg_trgm")

    # Verify the migration SQL creates it with the target's exact version and schema.
    gen_setup.assert_migration_sql(f'CREATE EXTENSION "pg_trgm" VERSION \'{version}\' SCHEMA "{schema}";')


def test_extension_drop(gen_setup: GenerateSetup) -> None:
    """
    Extension present in source but missing in target -> DROP EXTENSION.
    """
    # Install the extension on the source only.
    _create_extension(gen_setup.src, "pg_trgm")

    # Verify the migration SQL drops it.
    gen_setup.assert_migration_sql('DROP EXTENSION "pg_trgm";')


def test_extension_version_update(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but with different versions -> ALTER EXTENSION UPDATE.
    """
    # Pick an extension exposing multiple versions.
    name, old_version, new_version = _pick_multi_version_extension(gen_setup.src)

    # Install the old version on the source and the new version on the target.
    _create_extension(gen_setup.src, name, version=old_version)
    _create_extension(gen_setup.dst, name, version=new_version)

    # Verify the migration SQL updates to the target version.
    gen_setup.assert_migration_sql(f"ALTER EXTENSION \"{name}\" UPDATE TO '{new_version}';")


def test_extension_set_schema(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but in different schemas -> ALTER EXTENSION SET SCHEMA.
    """
    # Install a relocatable extension into different schemas on each side.
    _create_extension(gen_setup.src, "hstore")
    gen_setup.dst.execute("CREATE SCHEMA other")
    _create_extension(gen_setup.dst, "hstore", schema="other")

    # Verify the migration SQL relocates it to the target schema.
    gen_setup.assert_migration_sql('ALTER EXTENSION "hstore" SET SCHEMA "other";')
