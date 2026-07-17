from collections.abc import Callable
from typing import Protocol, TypeVar

from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._models import Index, Schema


class _HasIndexes(Protocol):
    """
    Any object owning an index map. Declared as a read-only property so a plain (frozen)
    dataclass attribute satisfies it -- the loader only mutates the dict in place, never
    reassigns the attribute itself.
    """

    @property
    def index_by_name(self) -> dict[str, Index]: ...


_T = TypeVar("_T", bound=_HasIndexes)


class _IndexRow(_QueryRow):
    schema_name: str
    relation_name: str  # the table or matview the index sits on
    index_name: str
    index_def: str
    index_canonical: str
    index_comment: str | None


async def _load_indexes(query_file: str, select_target: Callable[[Schema], dict[str, _T]]) -> None:
    """
    Shared body for the table-index and matview-index loaders. The two queries differ (a
    matview has no partitioning, primary keys or constraint-backed indexes to exclude), but
    the parsing and storage are identical; `select_target` picks the schema's table/matview
    mapping that owns the index.
    """
    for row in await run_introspection_query(query_file, _IndexRow):
        relation = select_target(context.db_introspection_result.schema_by_name[row.schema_name])[row.relation_name]
        relation.index_by_name[row.index_name] = Index(
            name=row.index_name,
            definition=row.index_def,
            canonical=row.index_canonical,
            comment=row.index_comment,
        )


async def load() -> None:
    """
    Indexes (standalone only; constraint-backed indexes are excluded).
    """
    await _load_indexes("indexes.sql", lambda schema: schema.table_by_name)
