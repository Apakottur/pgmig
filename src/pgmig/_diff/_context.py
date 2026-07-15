from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from pgmig._models import ColumnKey, DbInfo, ViewKey


def _retyped_column_refs(source: DbInfo, target: DbInfo) -> set[ColumnKey]:
    """
    Columns of tables present on both sides whose type changes between source and target.
    Postgres refuses ALTER COLUMN ... TYPE while a view reads the column, and -- unlike a
    dropped column -- a type change leaves the reading view's definition text unchanged, so
    the view-definition recreate path never catches it. The view diff intersects these with
    its view-on-column edges to decide which views to drop and recreate around the change.

    Source-side identity (a column read by a source view exists in the source). A serial
    change keeps the integer `type`, so it does not surface here; that is intentional -- a
    serial change is unsupported and raised by the table diff before applying.
    """
    refs: set[ColumnKey] = set()
    for schema_name in source.schema_by_name.keys() & target.schema_by_name.keys():
        src_tables = source.schema_by_name[schema_name].table_by_name
        dst_tables = target.schema_by_name[schema_name].table_by_name
        for table_name in src_tables.keys() & dst_tables.keys():
            dst_columns = {column.name: column for column in dst_tables[table_name].columns}
            for src_column in src_tables[table_name].columns:
                dst_column = dst_columns.get(src_column.name)
                if dst_column is not None and src_column.type != dst_column.type:
                    refs.add(ColumnKey(schema_name, table_name, src_column.name))
    return refs


def _compute_retyped_column_readers(source: DbInfo, target: DbInfo) -> set[ViewKey]:
    """
    Views and materialized views that read (in the source) a table column whose type changes
    between source and target. Such a reader must be dropped and recreated around the
    ALTER COLUMN ... TYPE (see pgmig._diff._core.retyped_column_readers for the full story).
    """
    retyped_columns = _retyped_column_refs(source, target)
    return {key for key, cols in source.view_column_dependencies.items() if cols & retyped_columns}


@dataclass(frozen=True)
class _ContextData:
    """
    Context data for the current diff generation.
    """

    # Databases.
    source: DbInfo
    target: DbInfo

    # Whether to emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with CONCURRENTLY.
    # Using CONCURRENTLY avoid blocking index read/write operations, but takes longer to execute and cannot be
    # run inside a transaction block.
    index_concurrently: bool

    # Names of extensions whose version mismatch is ignored: no ALTER EXTENSION ... UPDATE TO
    # is emitted for them. Empty (default) ignores none.
    ignore_extension_version: Sequence[str]

    # Suppress all ALTER ... OWNER TO statements.
    ignore_owner: bool

    # Views/matviews reading a table column whose type changes this diff. Derived from
    # source/target in __post_init__ (not a constructor arg) and shared by the three generators
    # that need it (view, matview, matview-index), so the O(tables x columns) scan runs once.
    retyped_column_readers: set[ViewKey] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "retyped_column_readers", _compute_retyped_column_readers(self.source, self.target))


# Context of the current diff generation.
_context: ContextVar[_ContextData] = ContextVar("pgmig_context")


class _Context:
    """
    Proxy over the context var. Generators import the `context` singleton and read
    `context.source` etc.; each access fetches the value set for the running diff.
    """

    @contextmanager
    def context_scope(
        self,
        *,
        source: DbInfo,
        target: DbInfo,
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
    def source(self) -> DbInfo:
        return _context.get().source

    @property
    def target(self) -> DbInfo:
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
    def retyped_column_readers(self) -> set[ViewKey]:
        return _context.get().retyped_column_readers


context = _Context()
