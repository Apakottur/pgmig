from collections import defaultdict
from dataclasses import dataclass

import psycopg
from psycopg import sql

from tests.fixtures.generate_setup import GenerateSetup
from tests.utils.db_utils import DbConnection


def _create_extension(
    conn: DbConnection,
    name: str,
    *,
    version: str | None = None,
    schema: str | None = None,
) -> None:
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


@dataclass(frozen=True)
class _ExtensionInfo:
    name: str
    version: str
    schema: str


def _get_installable_extension(conn: DbConnection) -> _ExtensionInfo:
    """
    Find a relocatable extension that can be installed, along with its default
    version. Relocatable extensions install into the current schema (public in a
    fresh database) and can be moved with ALTER EXTENSION ... SET SCHEMA.
    """
    rows = conn.execute(
        """
        SELECT ae.name, ae.default_version
        FROM pg_available_extensions ae
        JOIN pg_available_extension_versions av
        ON av.name = ae.name AND av.version = ae.default_version
        WHERE av.relocatable
        ORDER BY ae.name
        """
    )
    assert rows, "no relocatable extension available"
    name, default_version = rows[0]
    return _ExtensionInfo(name=name, version=default_version, schema="public")


@dataclass(frozen=True)
class _MultiVersionExtension:
    name: str
    min_version: str
    max_version: str


def _pick_multi_version_extension(conn: DbConnection) -> _MultiVersionExtension:
    """
    Find an extension exposing more than one installable version.
    """

    def _version_key(version: str) -> list[int]:
        """
        Sort key for Postgres extension versions (e.g. '1.10' sorts after '1.4').
        """
        return [int(part) for part in version.split(".")]

    # Get all available extension versions.
    rows = conn.execute("SELECT name, version FROM pg_available_extension_versions ORDER BY name")

    # Group versions by name.
    versions_by_name = defaultdict(list)
    for name, version in rows:
        versions_by_name[name].append(version)

    # Find the first extension with multiple versions.
    for name, versions in versions_by_name.items():
        if len(versions) > 1:
            sorted_versions = sorted(versions, key=_version_key)
            return _MultiVersionExtension(
                name=name,
                min_version=sorted_versions[0],
                max_version=sorted_versions[-1],
            )

    # No extension with multiple versions available.
    raise AssertionError("no extension with multiple versions available")


def test_extension_create(gen_setup: GenerateSetup) -> None:
    """
    Extension present in target but missing in source -> CREATE EXTENSION.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    # Install the extension on the target only.
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.version, schema=ext_info.schema)

    # Verify migration.
    gen_setup.assert_migration_sql(
        f'CREATE EXTENSION "{ext_info.name}" VERSION \'{ext_info.version}\' SCHEMA "{ext_info.schema}";'
    )


def test_extension_drop(gen_setup: GenerateSetup) -> None:
    """
    Extension present in source but missing in target -> DROP EXTENSION.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    # Install the extension on the source only.
    _create_extension(gen_setup.src, ext_info.name)

    # Verify migration.
    gen_setup.assert_migration_sql(f'DROP EXTENSION "{ext_info.name}";')


def test_extension_version_update(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but with different versions -> ALTER EXTENSION UPDATE.
    """
    # Pick an extension exposing multiple versions.
    ext_info = _pick_multi_version_extension(gen_setup.src)

    # Install the old version on the source and the new version on the target.
    _create_extension(gen_setup.src, ext_info.name, version=ext_info.min_version)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.max_version)

    # Verify migration.
    gen_setup.assert_migration_sql(f"ALTER EXTENSION \"{ext_info.name}\" UPDATE TO '{ext_info.max_version}';")


def test_extension_set_schema(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but in different schemas -> ALTER EXTENSION SET SCHEMA.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    # src - install in default schema
    _create_extension(gen_setup.src, ext_info.name)

    # dst - install in a new schema
    other_schema_name = "other"
    gen_setup.dst.execute(sql.SQL("CREATE SCHEMA {name}").format(name=sql.Identifier(other_schema_name)))
    _create_extension(gen_setup.dst, ext_info.name, schema=other_schema_name)

    # Verify migration.
    gen_setup.assert_migration_sql(f'ALTER EXTENSION "{ext_info.name}" SET SCHEMA "{other_schema_name}";')
