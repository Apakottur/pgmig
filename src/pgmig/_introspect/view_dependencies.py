from pgmig._introspect._context import context
from pgmig._introspect._core import _IntrospectionRow, run_introspection_query
from pgmig._keys import RelationKey


class _ViewDependencyRow(_IntrospectionRow):
    dependent_schema: str
    dependent_view: str
    referenced_schema: str
    referenced_view: str


async def load() -> None:
    """
    View-on-view edges: record, for each plain view that reads another plain view, the set
    of views it reads from. The view diff uses these to topologically order CREATE
    (dependencies first) and DROP (dependents first) within the view phases. Edges involving a
    materialized view live in matview_dependencies.py.
    """
    for row in await run_introspection_query("view_dependencies.sql", _ViewDependencyRow):
        dependent = RelationKey(row.dependent_schema, row.dependent_view)
        referenced = RelationKey(row.referenced_schema, row.referenced_view)
        context.db_introspection_result.view_dependencies.setdefault(dependent, set()).add(referenced)
