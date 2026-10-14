from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, run_introspection_query
from pgmig._introspect._rows import GrantRow, IntrospectionRowWithSchema, grants
from pgmig._models import Schema


class _SchemaRow(IntrospectionRowWithSchema):
    schema_comment: str | None
    schema_owner: str
    schema_grants: list[GrantRow]


def load_rows(rows: list[_SchemaRow]) -> None:
    """
    Schemas (user namespaces, excluding system and extension-owned ones).
    """
    for schema_row in rows:
        context().db_introspection_result.schema_by_name[schema_row.schema_name] = Schema(
            name=schema_row.schema_name,
            comment=schema_row.schema_comment,
            owner=schema_row.schema_owner,
            grants=grants(schema_row.schema_grants),
        )


async def load() -> None:
    """
    Run the query and load its rows.
    """
    load_rows(await run_introspection_query(IntrospectionQuery.SCHEMAS, _SchemaRow))
