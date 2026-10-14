from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, run_introspection_query
from pgmig._introspect._rows import IntrospectionRow
from pgmig._keys import RelationKey


class _ViewDependencyRow(IntrospectionRow):
    dependent_schema: str
    dependent_view: str
    referenced_schema: str
    referenced_view: str


def load_rows(rows: list[_ViewDependencyRow]) -> None:
    """
    View-on-view edges: record, for each plain view that reads another plain view, the set
    of views it reads from. The view diff uses these to topologically order CREATE
    (dependencies first) and DROP (dependents first) within the view phases. Edges involving a
    materialized view live in matview_dependencies.py.
    """
    for row in rows:
        dependent = RelationKey(row.dependent_schema, row.dependent_view)
        referenced = RelationKey(row.referenced_schema, row.referenced_view)
        context().db_introspection_result.view_dependencies.setdefault(dependent, set()).add(referenced)


async def load() -> None:
    """
    Run the query and load its rows.
    """
    load_rows(await run_introspection_query(IntrospectionQuery.VIEW_DEPENDENCIES, _ViewDependencyRow))
