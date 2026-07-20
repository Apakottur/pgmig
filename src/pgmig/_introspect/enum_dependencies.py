from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, IntrospectionRow, run_introspection_query
from pgmig._keys import EnumKey
from pgmig._models import EnumColumnDependency


class _EnumDependencyRow(IntrospectionRow):
    enum_schema: str
    enum_name: str
    table_schema: str
    table_name: str
    column_name: str
    is_array: bool
    is_generated: bool
    in_index: bool
    in_constraint: bool


async def load() -> None:
    """
    Enum-on-column edges: for each user enum, the table columns typed by it (directly or as an
    array). The enum diff uses these to rewrite dependent columns when an enum's values are
    removed or reordered, and to refuse the rewrite for columns it cannot handle.
    """
    for row in await run_introspection_query(IntrospectionQuery.ENUM_DEPENDENCIES, _EnumDependencyRow):
        key = EnumKey(row.enum_schema, row.enum_name)
        context.db_introspection_result.enum_column_dependencies.setdefault(key, []).append(
            EnumColumnDependency(
                schema=row.table_schema,
                table=row.table_name,
                column=row.column_name,
                is_array=row.is_array,
                is_generated=row.is_generated,
                in_index=row.in_index,
                in_constraint=row.in_constraint,
            )
        )
