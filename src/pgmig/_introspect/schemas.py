from pgmig._introspect._context import context
from pgmig._introspect._core import (
    GrantRow,
    IntrospectionQuery,
    IntrospectionRowWithSchema,
    grants,
    run_introspection_query,
)
from pgmig._models import Schema


class _SchemaRow(IntrospectionRowWithSchema):
    schema_comment: str | None
    schema_owner: str
    schema_grants: list[GrantRow]


async def load() -> None:
    """
    Schemas (user namespaces, excluding system and extension-owned ones).
    """
    for schema_row in await run_introspection_query(IntrospectionQuery.SCHEMAS, _SchemaRow):
        context.db_introspection_result.schema_by_name[schema_row.schema_name] = Schema(
            name=schema_row.schema_name,
            comment=schema_row.schema_comment,
            owner=schema_row.schema_owner,
            grants=grants(schema_row.schema_grants),
        )
