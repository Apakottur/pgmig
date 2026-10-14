from pgmig._introspect._context import context
from pgmig._introspect._core import Loader
from pgmig._introspect._rows import IntrospectionRow
from pgmig._keys import RelationKey


class _ViewDependencyRow(IntrospectionRow):
    dependent_schema: str
    dependent_view: str
    referenced_schema: str
    referenced_view: str


class ViewDependenciesLoader(Loader[_ViewDependencyRow]):
    """
    View-on-view edges: record, for each plain view that reads another plain view, the set
    of views it reads from. The view diff uses these to topologically order CREATE
    (dependencies first) and DROP (dependents first) within the view phases. Edges involving a
    materialized view live in matview_dependencies.py.
    """

    file_name = "view_dependencies.sql"
    model = _ViewDependencyRow

    @classmethod
    def process_rows(cls, rows: list[_ViewDependencyRow]) -> None:
        for row in rows:
            dependent = RelationKey(row.dependent_schema, row.dependent_view)
            referenced = RelationKey(row.referenced_schema, row.referenced_view)
            context().db_introspection_result.view_dependencies.setdefault(dependent, set()).add(referenced)
