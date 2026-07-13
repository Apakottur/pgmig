from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from pgmig._build._engine import build_db_info
from pgmig._diff._context import context
from pgmig._diff._engine import generate_migration_sql
from pgmig._errors import PgmigError
from pgmig._models import DbInfo


def _validate_omit_schema(omit_schema: str, source: DbInfo, target: DbInfo) -> None:
    """
    Confirm both databases contain exactly the one user schema named by omit_schema.

    Introspection already excludes system and extension-owned schemas, so schema_by_name
    holds only user schemas. Requiring the named schema to be the sole one on both sides
    means an unqualified name can never be ambiguous or point at the wrong schema.
    """
    for label, db in (("source", source), ("target", target)):
        names = set(db.schema_by_name)
        if names != {omit_schema}:
            raise PgmigError(
                f"omit_schema {omit_schema!r} requires the {label} database to contain exactly "
                f"that one user schema, but found: {sorted(names)}."
            )


def generate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    ignore_extension_version: Sequence[str] = (),
    omit_schema: str | None = None,
) -> str:
    """
    Generate the migration SQL between the given source and target databases.

    Args:
        source: The source database DSN.
        target: The target database DSN.
        index_concurrently: Whether to emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with CONCURRENTLY.
                            Using CONCURRENTLY avoids blocking index read/write operations, but takes longer to execute
                            and cannot be run inside a transaction block.
        ignore_extension_version: Names of extensions whose version mismatch is ignored: no ALTER EXTENSION ...
                                  UPDATE TO is emitted for them. Empty (default) ignores none.
        omit_schema: Omit this schema's qualifier from the emitted SQL, provided it is the only user schema in
                     both databases (otherwise a PgmigError is raised). Introspection then runs with the schema
                     on the search_path so server-side definitions are unqualified too.
    """
    # Introspect both databases concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        source_future = executor.submit(build_db_info, source, search_path_schema=omit_schema)
        target_future = executor.submit(build_db_info, target, search_path_schema=omit_schema)
        source_db_info = source_future.result()
        target_db_info = target_future.result()

    # Confirm the omitted schema is unambiguously the only user schema before diffing.
    if omit_schema is not None:
        _validate_omit_schema(omit_schema, source_db_info, target_db_info)

    # Generate migration SQL.
    with context.context_scope(
        source=source_db_info,
        target=target_db_info,
        index_concurrently=index_concurrently,
        ignore_extension_version=ignore_extension_version,
        omit_schema=omit_schema,
    ):
        return generate_migration_sql()
