from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._models import Index


class _IndexRow(_QueryRow):
    schema_name: str
    table_name: str
    index_name: str
    index_def: str
    index_canonical: str
    index_comment: str | None


def load() -> None:
    """
    Indexes (standalone only; constraint-backed indexes are excluded).
    """
    for index_row in run_introspection_query("indexes.sql", _IndexRow):
        table = context.db_info.schema_by_name[index_row.schema_name].table_by_name[index_row.table_name]
        table.index_by_name[index_row.index_name] = Index(
            name=index_row.index_name,
            definition=index_row.index_def,
            canonical=index_row.index_canonical,
            comment=index_row.index_comment,
        )
