from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, run_introspection_query
from pgmig._introspect._rows import IntrospectionRow
from pgmig._keys import CompositeTypeKey


class _CompositeTypeDependencyRow(IntrospectionRow):
    dependent_schema: str
    dependent_type: str
    referenced_schema: str
    referenced_type: str


def load_rows(rows: list[_CompositeTypeDependencyRow]) -> None:
    """
    Composite-on-composite edges: record, for each standalone composite type with a field of
    another composite type, the set of composite types it depends on. The composite-type diff
    uses these to topologically order CREATE (dependencies first) and DROP (dependents first)
    within the type phases.
    """
    for row in rows:
        dependent = CompositeTypeKey(row.dependent_schema, row.dependent_type)
        referenced = CompositeTypeKey(row.referenced_schema, row.referenced_type)
        context().db_introspection_result.composite_type_dependencies.setdefault(dependent, set()).add(referenced)


async def load() -> None:
    """
    Run the query and load its rows.
    """
    load_rows(
        await run_introspection_query(IntrospectionQuery.COMPOSITE_TYPE_DEPENDENCIES, _CompositeTypeDependencyRow)
    )
