import asyncio
from collections.abc import Sequence

from pgmig._diff._context import context
from pgmig._diff._engine import generate_migration_sql
from pgmig._introspect._engine import introspect_db
from pgmig._models import DbInfo


def generate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    ignore_extension_version: Sequence[str] = (),
    ignore_owner: bool = False,
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
        ignore_owner: Suppress all ALTER ... OWNER TO statements.
    """
    # Introspect both databases concurrently.
    source_db_info, target_db_info = asyncio.gather(introspect_db(source), introspect_db(target))

    # Generate migration SQL.
    with context.context_scope(
        source=source_db_info,
        target=target_db_info,
        index_concurrently=index_concurrently,
        ignore_extension_version=ignore_extension_version,
        ignore_owner=ignore_owner,
    ):
        return generate_migration_sql()
