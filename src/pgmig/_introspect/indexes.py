from collections.abc import Callable
from typing import Protocol, TypeVar

from pgmig._introspect._context import context
from pgmig._introspect._rows import IntrospectionRowWithSchema
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


class IndexRow(IntrospectionRowWithSchema):
    relation_name: str  # the table or matview the index sits on
    index_name: str
    index_def: str
    index_canonical: str
    index_dependency_columns: list[str] | None
    index_comment: str | None


def _load_indexes(rows: list[IndexRow], select_target: Callable[[Schema], dict[str, _T]]) -> None:
    """
    Shared body for the table-index and matview-index loaders. The two queries differ (a
    matview has no partitioning, primary keys or constraint-backed indexes to exclude), but
    the parsing and storage are identical; `select_target` picks the schema's table/matview
    mapping that owns the index.
    """
    for row in rows:
        relation = select_target(context().db_introspection_result.schema_by_name[row.schema_name])[row.relation_name]
        relation.index_by_name[row.index_name] = Index(
            name=row.index_name,
            definition=row.index_def,
            canonical=row.index_canonical,
            dependency_columns=frozenset(row.index_dependency_columns or ()),
            comment=row.index_comment,
        )


def load_rows(rows: list[IndexRow]) -> None:
    """
    Indexes (standalone only; constraint-backed indexes are excluded).
    """
    _load_indexes(rows, lambda schema: schema.table_by_name)
