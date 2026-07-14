from collections import defaultdict
from dataclasses import dataclass

from psycopg import sql

from pgmig import generate
from tests.api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import DbConnection


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

    conn.execute(stmt)


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
        f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE;'
    )


def test_extension_owned_table_not_recreated(gen_setup: GenerateSetup) -> None:
    """
    A table an extension owns directly (as PostGIS owns spatial_ref_sys in public) must
    not be re-emitted: CREATE EXTENSION already creates it, plus its indexes and
    constraints, so a CREATE TABLE would fail with "relation already exists". The
    migration must contain only the CREATE EXTENSION.

    Extension ownership is reproduced with ALTER EXTENSION ... ADD, which records the
    same pg_depend deptype='e' membership PostGIS relies on -- no PostGIS image needed.
    """
    ext_info = _get_installable_extension(gen_setup.dst)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.version, schema=ext_info.schema)

    # A table with a primary key and a secondary index. Extension membership is
    # recorded on the table; the constraint and index are excluded because their
    # owning table is extension-owned, exercising all three query exclusions.
    gen_setup.dst.execute("CREATE TABLE spatial_ref_sys (srid integer PRIMARY KEY, name text)")
    gen_setup.dst.execute("CREATE INDEX spatial_ref_sys_name_idx ON spatial_ref_sys (name)")
    ext = sql.Identifier(ext_info.name)
    gen_setup.dst.execute(sql.SQL("ALTER EXTENSION {ext} ADD TABLE spatial_ref_sys").format(ext=ext))

    gen_setup.assert_migration_sql(
        f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE;'
    )


def test_user_trigger_on_extension_owned_table(gen_setup: GenerateSetup) -> None:
    """
    A user trigger on a table an extension owns (as an audit trigger on PostGIS
    spatial_ref_sys would be) must be excluded: the owning table is extension-managed
    and dropped from the model, so triggers.sql needs the owning-table exclusion or the
    loader raises KeyError on the missing table. Mirrors the index/constraint exclusion.

    The trigger function is made an extension member too so only CREATE EXTENSION is
    expected; the trigger itself stays user-owned and is the object exercising the bug.
    """
    ext_info = _get_installable_extension(gen_setup.dst)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.version, schema=ext_info.schema)

    gen_setup.dst.execute("CREATE TABLE spatial_ref_sys (srid integer PRIMARY KEY, name text)")
    gen_setup.dst.execute("CREATE FUNCTION spatial_audit() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END'")
    gen_setup.dst.execute(
        "CREATE TRIGGER spatial_audit_trg BEFORE INSERT ON spatial_ref_sys "
        "FOR EACH ROW EXECUTE FUNCTION spatial_audit()"
    )
    ext = sql.Identifier(ext_info.name)
    gen_setup.dst.execute(sql.SQL("ALTER EXTENSION {ext} ADD TABLE spatial_ref_sys").format(ext=ext))
    gen_setup.dst.execute(sql.SQL("ALTER EXTENSION {ext} ADD FUNCTION spatial_audit()").format(ext=ext))

    gen_setup.assert_migration_sql(
        f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE;'
    )


def test_user_function_in_extension_owned_schema(gen_setup: GenerateSetup) -> None:
    """
    A user function inside a schema an extension owns must be excluded: the schema is
    extension-managed and dropped from the model, so functions.sql needs the
    namespace-level exclusion or the loader raises KeyError on the missing schema.
    """
    ext_info = _get_installable_extension(gen_setup.dst)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.version, schema=ext_info.schema)

    gen_setup.dst.execute("CREATE SCHEMA ext_schema")
    ext = sql.Identifier(ext_info.name)
    gen_setup.dst.execute(sql.SQL("ALTER EXTENSION {ext} ADD SCHEMA ext_schema").format(ext=ext))
    gen_setup.dst.execute("CREATE FUNCTION ext_schema.helper() RETURNS integer LANGUAGE sql AS 'SELECT 1'")

    gen_setup.assert_migration_sql(
        f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE;'
    )


def test_user_enum_in_extension_owned_schema(gen_setup: GenerateSetup) -> None:
    """
    A user enum inside a schema an extension owns must be excluded: the schema is
    extension-managed and dropped from the model, so enums.sql needs the namespace-level
    exclusion or the loader raises KeyError on the missing schema.
    """
    ext_info = _get_installable_extension(gen_setup.dst)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.version, schema=ext_info.schema)

    gen_setup.dst.execute("CREATE SCHEMA ext_schema")
    ext = sql.Identifier(ext_info.name)
    gen_setup.dst.execute(sql.SQL("ALTER EXTENSION {ext} ADD SCHEMA ext_schema").format(ext=ext))
    gen_setup.dst.execute("CREATE TYPE ext_schema.mood AS ENUM ('happy', 'sad')")

    gen_setup.assert_migration_sql(
        f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE;'
    )


def test_extension_owned_sequence_not_recreated(gen_setup: GenerateSetup) -> None:
    """
    A standalone sequence an extension owns directly must be excluded: CREATE EXTENSION
    recreates it, so re-emitting CREATE SEQUENCE would fail. The sequence lives in a user
    schema and is not column-owned, so only sequences.sql's self-leg exclusion can drop it.
    """
    ext_info = _get_installable_extension(gen_setup.dst)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.version, schema=ext_info.schema)

    gen_setup.dst.execute("CREATE SEQUENCE ext_seq")
    ext = sql.Identifier(ext_info.name)
    gen_setup.dst.execute(sql.SQL("ALTER EXTENSION {ext} ADD SEQUENCE ext_seq").format(ext=ext))

    gen_setup.assert_migration_sql(
        f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE;'
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


def test_ignore_extension_version_list_matching_suppresses_update(gen_setup: GenerateSetup) -> None:
    """
    A list naming the extension suppresses only that extension's version update.
    """
    ext_info = _pick_multi_version_extension(gen_setup.src)
    _create_extension(gen_setup.src, ext_info.name, version=ext_info.min_version)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.max_version)

    sql_out = generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, ignore_extension_version=[ext_info.name])

    assert sql_out == ""


def test_ignore_extension_version_list_non_matching_still_updates(gen_setup: GenerateSetup) -> None:
    """
    A list that does not name the extension leaves its version update in place.
    """
    ext_info = _pick_multi_version_extension(gen_setup.src)
    _create_extension(gen_setup.src, ext_info.name, version=ext_info.min_version)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.max_version)

    sql_out = generate(
        source=gen_setup.src.dsn, target=gen_setup.dst.dsn, ignore_extension_version=["some_other_extension"]
    )

    assert sql_out == f"ALTER EXTENSION \"{ext_info.name}\" UPDATE TO '{ext_info.max_version}';"


def test_extension_set_schema(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but in different schemas -> ALTER EXTENSION SET SCHEMA.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    # Create the target schema on both sides so only the extension move is diffed.
    other_schema_name = "other"
    create_schema = sql.SQL("CREATE SCHEMA {name}").format(name=sql.Identifier(other_schema_name))
    gen_setup.execute_both(create_schema)

    # src - install in default schema, dst - install in the new schema.
    _create_extension(gen_setup.src, ext_info.name)
    _create_extension(gen_setup.dst, ext_info.name, schema=other_schema_name)

    # Verify migration.
    gen_setup.assert_migration_sql(f'ALTER EXTENSION "{ext_info.name}" SET SCHEMA "{other_schema_name}";')


def test_extension_dropped_after_dependent_table(gen_setup: GenerateSetup) -> None:
    """
    A table uses a type provided by an extension, and both are dropped. DROP EXTENSION
    must run after DROP TABLE -- dropping the extension first fails because the table's
    column still depends on it ("other objects depend on it").
    """
    gen_setup.src.execute("CREATE EXTENSION citext")
    gen_setup.src.execute("CREATE TABLE u (e citext)")

    gen_setup.assert_migration_sql(
        [
            'DROP TABLE "public"."u";',
            'DROP EXTENSION "citext";',
        ]
    )


def test_extension_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Extension present on both sides with differing comments -> COMMENT ON EXTENSION with
    the target's. (A newly created extension already carries its control-file comment, so
    comments are only synced for the present-on-both case.)
    """
    ext_info = _get_installable_extension(gen_setup.dst)
    _create_extension(gen_setup.src, ext_info.name, version=ext_info.version, schema=ext_info.schema)
    _create_extension(gen_setup.dst, ext_info.name, version=ext_info.version, schema=ext_info.schema)
    gen_setup.dst.execute(sql.SQL("COMMENT ON EXTENSION {name} IS 'custom'").format(name=sql.Identifier(ext_info.name)))

    gen_setup.assert_migration_sql(f"COMMENT ON EXTENSION \"{ext_info.name}\" IS 'custom';")
