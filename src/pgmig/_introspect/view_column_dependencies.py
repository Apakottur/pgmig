from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, run_introspection_query
from pgmig._introspect._rows import IntrospectionRow
from pgmig._keys import ColumnKey, RelationKey


class _ViewColumnDependencyRow(IntrospectionRow):
    view_schema: str
    view_name: str
    table_schema: str
    table_name: str
    column_name: str


def load_rows(rows: list[_ViewColumnDependencyRow]) -> None:
    """
    View-on-column edges: record, for each view or materialized view, the set of table
    columns it reads. The view and matview diffs use these to drop and recreate a (mat)view
    around a change (type change, drop) to a column it depends on, since Postgres refuses to
    alter or drop a column a view or matview reads.
    """
    for row in rows:
        view = RelationKey(row.view_schema, row.view_name)
        column = ColumnKey(row.table_schema, row.table_name, row.column_name)
        context().db_introspection_result.view_column_dependencies.setdefault(view, set()).add(column)


async def load() -> None:
    """
    Run the query and load its rows.
    """
    load_rows(await run_introspection_query(IntrospectionQuery.VIEW_COLUMN_DEPENDENCIES, _ViewColumnDependencyRow))
