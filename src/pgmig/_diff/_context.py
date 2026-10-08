from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cached_property
from typing import cast

from pgmig._diff._relations import recreated_matview_keys, recreated_view_keys
from pgmig._keys import ColumnKey, RelationKey
from pgmig._models import DbIntrospectionResult


def _get_retyped_column_readers(source: DbIntrospectionResult, target: DbIntrospectionResult) -> set[RelationKey]:
    """
    Views/matviews that read (in the source) a table column whose type changes between source
    and target. Such a reader must be dropped and recreated around the ALTER COLUMN ... TYPE:
    Postgres refuses the alter while a view reads the column, and -- unlike a dropped column --
    a type change leaves the reader's definition text unchanged, so the view-definition recreate
    path never catches it. Only the source view-on-column edges catch it.

    Computed lazily on first access and cached for the diff scope (see
    ContextData.retyped_column_readers), shared by the view and matview recreate sets, so the
    O(tables x columns) scan runs at most once -- and never at all for a diff with no views.

    Source-side identity (a column read by a source view exists in the source). A serial change
    keeps the integer `type`, so it does not surface here; that is intentional -- a serial change
    is unsupported and raised by the table diff before applying.
    """
    retyped_columns: set[ColumnKey] = set()
    for schema_name in source.schema_by_name.keys() & target.schema_by_name.keys():
        src_tables = source.schema_by_name[schema_name].table_by_name
        dst_tables = target.schema_by_name[schema_name].table_by_name
        for table_name in src_tables.keys() & dst_tables.keys():
            dst_columns = dst_tables[table_name].column_by_name
            for src_column in src_tables[table_name].columns:
                dst_column = dst_columns.get(src_column.name)
                if dst_column is not None and src_column.type != dst_column.type:
                    retyped_columns.add(ColumnKey(schema_name, table_name, src_column.name))
    return {key for key, cols in source.view_column_dependencies.items() if cols & retyped_columns}


@dataclass(frozen=True)
class ContextData:
    """
    Context data for the current diff generation.
    """

    # Databases.
    source: DbIntrospectionResult
    target: DbIntrospectionResult

    # Whether to emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with CONCURRENTLY.
    # Using CONCURRENTLY avoid blocking index read/write operations, but takes longer to execute and cannot be
    # run inside a transaction block.
    index_concurrently: bool

    # Whether to emit SET NOT NULL on an existing column through a NOT VALID CHECK (col IS NOT NULL) that is
    # validated, then dropped once the column is NOT NULL. The validated CHECK lets SET NOT NULL skip its
    # full-table scan, so the ACCESS EXCLUSIVE lock is held only briefly.
    safe_not_null: bool

    # Names of extensions whose version mismatch is ignored: no ALTER EXTENSION ... UPDATE TO
    # is emitted for them. Empty (default) ignores none.
    ignore_extension_version: Sequence[str]

    # Emit ALTER ... OWNER TO statements to reconcile ownership. Off by default: ownership
    # references cluster-level roles that routinely differ across environments.
    include_owner: bool

    # Diff named-role GRANT / REVOKE (PUBLIC grants are always diffed regardless).
    include_grants: bool

    @cached_property
    def retyped_column_readers(self) -> set[RelationKey]:
        return _get_retyped_column_readers(self.source, self.target)

    @cached_property
    def recreated_view_keys(self) -> set[RelationKey]:
        return recreated_view_keys(self.source, self.target, self.retyped_column_readers)

    @cached_property
    def recreated_matview_keys(self) -> set[RelationKey]:
        return recreated_matview_keys(self.source, self.target, self.retyped_column_readers, self.recreated_view_keys)


# Context of the current diff generation.
_context: ContextVar[ContextData] = ContextVar("pgmig_context")


@contextmanager
def context_scope(data: ContextData) -> Iterator[None]:
    """
    Run the enclosed diff generation with the given context data.
    """
    token = _context.set(data)
    try:
        yield
    finally:
        _context.reset(token)


class _ContextProxy:
    """
    Forwards attribute reads to the context data of the current diff scope.
    """

    def __getattr__(self, name: str) -> object:
        return getattr(_context.get(), name)


# Typed as the data it forwards to, so attribute reads stay type-checked.
context = cast("ContextData", _ContextProxy())
