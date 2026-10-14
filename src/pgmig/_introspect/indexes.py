from collections.abc import Mapping
from typing import Protocol

from pgmig._introspect._context import context
from pgmig._introspect._core import Loader
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


class _IndexRow(IntrospectionRowWithSchema):
    relation_name: str  # the table or matview the index sits on
    index_name: str
    index_def: str
    index_canonical: str
    index_dependency_columns: list[str] | None
    index_comment: str | None


class IndexesLoader(Loader[_IndexRow]):
    """
    Indexes on tables (standalone only; constraint-backed indexes are excluded).
    """

    file_name = "indexes.sql"
    model = _IndexRow

    @classmethod
    def get_relations(cls, schema: Schema) -> Mapping[str, _HasIndexes]:
        """
        Get the schema's relations that own the indexes, by name.
        """
        return schema.table_by_name

    @classmethod
    def process_rows(cls, rows: list[_IndexRow]) -> None:
        for row in rows:
            schema = context().db_introspection_result.schema_by_name[row.schema_name]
            relation = cls.get_relations(schema)[row.relation_name]
            relation.index_by_name[row.index_name] = Index(
                name=row.index_name,
                definition=row.index_def,
                canonical=row.index_canonical,
                dependency_columns=frozenset(row.index_dependency_columns or ()),
                comment=row.index_comment,
            )
