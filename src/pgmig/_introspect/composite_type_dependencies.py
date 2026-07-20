from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, _IntrospectionRow, run_introspection_query
from pgmig._keys import CompositeTypeKey


class _CompositeTypeDependencyRow(_IntrospectionRow):
    dependent_schema: str
    dependent_type: str
    referenced_schema: str
    referenced_type: str


async def load() -> None:
    """
    Composite-on-composite edges: record, for each standalone composite type with a field of
    another composite type, the set of composite types it depends on. The composite-type diff
    uses these to topologically order CREATE (dependencies first) and DROP (dependents first)
    within the type phases.
    """
    for row in await run_introspection_query(
        IntrospectionQuery.COMPOSITE_TYPE_DEPENDENCIES, _CompositeTypeDependencyRow
    ):
        dependent = CompositeTypeKey(row.dependent_schema, row.dependent_type)
        referenced = CompositeTypeKey(row.referenced_schema, row.referenced_type)
        context.db_introspection_result.composite_type_dependencies.setdefault(dependent, set()).add(referenced)
