from pgmig._introspect._context import context
from pgmig._introspect._core import Loader
from pgmig._introspect._rows import IntrospectionRow
from pgmig._keys import ColumnKey, RelationKey


class _ViewColumnDependencyRow(IntrospectionRow):
    view_schema: str
    view_name: str
    table_schema: str
    table_name: str
    column_name: str


class ViewColumnDependenciesLoader(Loader[_ViewColumnDependencyRow]):
    """
    View-on-column edges: record, for each view or materialized view, the set of table
    columns it reads. The view and matview diffs use these to drop and recreate a (mat)view
    around a change (type change, drop) to a column it depends on, since Postgres refuses to
    alter or drop a column a view or matview reads.
    """

    file_name = "view_column_dependencies.sql"
    model = _ViewColumnDependencyRow

    def process_rows(self, rows: list[_ViewColumnDependencyRow]) -> None:
        for row in rows:
            view = RelationKey(row.view_schema, row.view_name)
            column = ColumnKey(row.table_schema, row.table_name, row.column_name)
            context().db_introspection_result.view_column_dependencies.setdefault(view, set()).add(column)
