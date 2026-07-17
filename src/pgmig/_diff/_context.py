from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cached_property

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
    _ContextData.retyped_column_readers), shared by the view diff, the matview diff, and the
    matview-index differ, so the O(tables x columns) scan runs at most once -- and never at all
    for a diff with no views.

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
class _ContextData:
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

    # Names of extensions whose version mismatch is ignored: no ALTER EXTENSION ... UPDATE TO
    # is emitted for them. Empty (default) ignores none.
    ignore_extension_version: Sequence[str]

    # Suppress all ALTER ... OWNER TO statements.
    ignore_owner: bool

    @cached_property
    def retyped_column_readers(self) -> set[RelationKey]:
        return _get_retyped_column_readers(self.source, self.target)


# Context of the current diff generation.
_context: ContextVar[_ContextData] = ContextVar("pgmig_context")


class _Context:
    """
    Singleton class for the diff context.
    """

    @contextmanager
    def context_scope(
        self,
        *,
        source: DbIntrospectionResult,
        target: DbIntrospectionResult,
        index_concurrently: bool,
        ignore_extension_version: Sequence[str],
        ignore_owner: bool,
    ) -> Iterator[None]:
        token = _context.set(
            _ContextData(
                source=source,
                target=target,
                index_concurrently=index_concurrently,
                ignore_extension_version=ignore_extension_version,
                ignore_owner=ignore_owner,
            )
        )
        try:
            yield
        finally:
            _context.reset(token)

    @property
    def source(self) -> DbIntrospectionResult:
        return _context.get().source

    @property
    def target(self) -> DbIntrospectionResult:
        return _context.get().target

    @property
    def index_concurrently(self) -> bool:
        return _context.get().index_concurrently

    @property
    def ignore_extension_version(self) -> Sequence[str]:
        return _context.get().ignore_extension_version

    @property
    def ignore_owner(self) -> bool:
        return _context.get().ignore_owner

    @property
    def retyped_column_readers(self) -> set[RelationKey]:
        return _context.get().retyped_column_readers


context = _Context()
