from collections import defaultdict
from dataclasses import dataclass

from pgmig import generate
from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import DbConnection


def _create_extension(name: str, *, version: str | None = None, schema: str | None = None) -> str:
    """
    Build a CREATE EXTENSION statement, optionally pinning its version and/or schema.
    """
    stmt = f"CREATE EXTENSION {name}"
    if version is not None:
        stmt += f" VERSION '{version}'"
    if schema is not None:
        stmt += f" SCHEMA {schema}"
    return stmt


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


async def test_extension_create(gen_setup: GenerateSetup) -> None:
    """
    Extension present in target but missing in source -> CREATE EXTENSION.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    await gen_setup.assert_diff(
        src=[],
        dst=[_create_extension(ext_info.name, version=ext_info.version, schema=ext_info.schema)],
        diff=[f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE'],
    )


async def test_extension_owned_table_not_recreated(gen_setup: GenerateSetup) -> None:
    """
    A table an extension owns directly (as PostGIS owns spatial_ref_sys in public) must
    not be re-emitted: CREATE EXTENSION already creates it, plus its indexes and
    constraints, so a CREATE TABLE would fail with "relation already exists". The
    migration must contain only the CREATE EXTENSION.

    Extension ownership is reproduced with ALTER EXTENSION ... ADD, which records the
    same pg_depend deptype='e' membership PostGIS relies on -- no PostGIS image needed.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    # A table with a primary key and a secondary index. Extension membership is
    # recorded on the table; the constraint and index are excluded because their
    # owning table is extension-owned, exercising all three query exclusions.
    await gen_setup.assert_diff(
        src=[],
        dst=[
            _create_extension(ext_info.name, version=ext_info.version, schema=ext_info.schema),
            "CREATE TABLE spatial_ref_sys (srid integer PRIMARY KEY, name text)",
            "CREATE INDEX spatial_ref_sys_name_idx ON spatial_ref_sys (name)",
            f"ALTER EXTENSION {ext_info.name} ADD TABLE spatial_ref_sys",
        ],
        diff=[f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE'],
    )


async def test_user_trigger_on_extension_owned_table(gen_setup: GenerateSetup) -> None:
    """
    A user trigger on a table an extension owns (as an audit trigger on PostGIS
    spatial_ref_sys would be) must be excluded: the owning table is extension-managed
    and dropped from the model, so triggers.sql needs the owning-table exclusion or the
    loader raises KeyError on the missing table. Mirrors the index/constraint exclusion.

    The trigger function is made an extension member too so only CREATE EXTENSION is
    expected; the trigger itself stays user-owned and is the object exercising the bug.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    await gen_setup.assert_diff(
        src=[],
        dst=[
            _create_extension(ext_info.name, version=ext_info.version, schema=ext_info.schema),
            "CREATE TABLE spatial_ref_sys (srid integer PRIMARY KEY, name text)",
            "CREATE FUNCTION spatial_audit() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END'",
            "CREATE TRIGGER spatial_audit_trg BEFORE INSERT ON spatial_ref_sys "
            "FOR EACH ROW EXECUTE FUNCTION spatial_audit()",
            f"ALTER EXTENSION {ext_info.name} ADD TABLE spatial_ref_sys",
            f"ALTER EXTENSION {ext_info.name} ADD FUNCTION spatial_audit()",
        ],
        diff=[f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE'],
    )


async def test_user_function_in_extension_owned_schema(gen_setup: GenerateSetup) -> None:
    """
    A user function inside a schema an extension owns must be excluded: the schema is
    extension-managed and dropped from the model, so functions.sql needs the
    namespace-level exclusion or the loader raises KeyError on the missing schema.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    await gen_setup.assert_diff(
        src=[],
        dst=[
            _create_extension(ext_info.name, version=ext_info.version, schema=ext_info.schema),
            "CREATE SCHEMA ext_schema",
            f"ALTER EXTENSION {ext_info.name} ADD SCHEMA ext_schema",
            "CREATE FUNCTION ext_schema.helper() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
        ],
        diff=[f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE'],
    )


async def test_user_enum_in_extension_owned_schema(gen_setup: GenerateSetup) -> None:
    """
    A user enum inside a schema an extension owns must be excluded: the schema is
    extension-managed and dropped from the model, so enums.sql needs the namespace-level
    exclusion or the loader raises KeyError on the missing schema.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    await gen_setup.assert_diff(
        src=[],
        dst=[
            _create_extension(ext_info.name, version=ext_info.version, schema=ext_info.schema),
            "CREATE SCHEMA ext_schema",
            f"ALTER EXTENSION {ext_info.name} ADD SCHEMA ext_schema",
            "CREATE TYPE ext_schema.mood AS ENUM ('happy', 'sad')",
        ],
        diff=[f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE'],
    )


async def test_extension_owned_sequence_not_recreated(gen_setup: GenerateSetup) -> None:
    """
    A standalone sequence an extension owns directly must be excluded: CREATE EXTENSION
    recreates it, so re-emitting CREATE SEQUENCE would fail. The sequence lives in a user
    schema and is not column-owned, so only sequences.sql's self-leg exclusion can drop it.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    await gen_setup.assert_diff(
        src=[],
        dst=[
            _create_extension(ext_info.name, version=ext_info.version, schema=ext_info.schema),
            "CREATE SEQUENCE ext_seq",
            f"ALTER EXTENSION {ext_info.name} ADD SEQUENCE ext_seq",
        ],
        diff=[f'CREATE EXTENSION IF NOT EXISTS "{ext_info.name}" SCHEMA "{ext_info.schema}" CASCADE'],
    )


async def test_extension_drop(gen_setup: GenerateSetup) -> None:
    """
    Extension present in source but missing in target -> DROP EXTENSION.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    await gen_setup.assert_diff(
        src=[_create_extension(ext_info.name)],
        dst=[],
        diff=[f'DROP EXTENSION "{ext_info.name}"'],
    )


async def test_extension_version_update(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but with different versions -> ALTER EXTENSION UPDATE.
    """
    ext_info = _pick_multi_version_extension(gen_setup.src)

    await gen_setup.assert_diff(
        src=[_create_extension(ext_info.name, version=ext_info.min_version)],
        dst=[_create_extension(ext_info.name, version=ext_info.max_version)],
        diff=[f"ALTER EXTENSION \"{ext_info.name}\" UPDATE TO '{ext_info.max_version}'"],
    )


def test_ignore_extension_version_list_matching_suppresses_update(gen_setup: GenerateSetup) -> None:
    """
    A list naming the extension suppresses only that extension's version update.
    """
    ext_info = _pick_multi_version_extension(gen_setup.src)
    gen_setup.src.execute(_create_extension(ext_info.name, version=ext_info.min_version))  # ty: ignore[invalid-argument-type]
    gen_setup.dst.execute(_create_extension(ext_info.name, version=ext_info.max_version))  # ty: ignore[invalid-argument-type]

    sql_out = generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, ignore_extension_version=[ext_info.name])

    assert sql_out == ""


def test_ignore_extension_version_list_non_matching_still_updates(gen_setup: GenerateSetup) -> None:
    """
    A list that does not name the extension leaves its version update in place.
    """
    ext_info = _pick_multi_version_extension(gen_setup.src)
    gen_setup.src.execute(_create_extension(ext_info.name, version=ext_info.min_version))  # ty: ignore[invalid-argument-type]
    gen_setup.dst.execute(_create_extension(ext_info.name, version=ext_info.max_version))  # ty: ignore[invalid-argument-type]

    sql_out = generate(
        source=gen_setup.src.dsn, target=gen_setup.dst.dsn, ignore_extension_version=["some_other_extension"]
    )

    assert sql_out == f"ALTER EXTENSION \"{ext_info.name}\" UPDATE TO '{ext_info.max_version}';"


async def test_extension_set_schema(gen_setup: GenerateSetup) -> None:
    """
    Extension present in both but in different schemas -> ALTER EXTENSION SET SCHEMA.
    """
    ext_info = _get_installable_extension(gen_setup.dst)

    await gen_setup.assert_diff(
        # Create the target schema on both sides so only the extension move is diffed.
        both=["CREATE SCHEMA other"],
        src=[_create_extension(ext_info.name)],
        dst=[_create_extension(ext_info.name, schema="other")],
        diff=[f'ALTER EXTENSION "{ext_info.name}" SET SCHEMA "other"'],
    )


async def test_extension_dropped_after_dependent_table(gen_setup: GenerateSetup) -> None:
    """
    A table uses a type provided by an extension, and both are dropped. DROP EXTENSION
    must run after DROP TABLE -- dropping the extension first fails because the table's
    column still depends on it ("other objects depend on it").
    """
    await gen_setup.assert_diff(
        src=["CREATE EXTENSION citext", "CREATE TABLE u (e citext)"],
        dst=[],
        diff=[
            'DROP TABLE "public"."u"',
            'DROP EXTENSION "citext"',
        ],
    )


async def test_extension_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Extension present on both sides with differing comments -> COMMENT ON EXTENSION with
    the target's. (A newly created extension already carries its control-file comment, so
    comments are only synced for the present-on-both case.)
    """
    ext_info = _get_installable_extension(gen_setup.dst)
    create = _create_extension(ext_info.name, version=ext_info.version, schema=ext_info.schema)

    await gen_setup.assert_diff(
        src=[create],
        dst=[create, f"COMMENT ON EXTENSION {ext_info.name} IS 'custom'"],
        diff=[f"COMMENT ON EXTENSION \"{ext_info.name}\" IS 'custom'"],
    )
