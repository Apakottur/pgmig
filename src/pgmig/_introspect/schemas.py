from pgmig._introspect._context import context
from pgmig._introspect._core import (
    IntrospectionQuery,
    _IntrospectionRow,
    _IntrospectionRowWithSchema,
    run_introspection_query,
)
from pgmig._models import Grant, Schema


class _GrantRow(_IntrospectionRow):
    grantee: str
    privilege: str
    grantable: bool


class _SchemaRow(_IntrospectionRowWithSchema):
    schema_comment: str | None
    schema_owner: str
    schema_grants: list[_GrantRow]


async def load() -> None:
    """
    Schemas (user namespaces, excluding system and extension-owned ones).
    """
    for schema_row in await run_introspection_query(IntrospectionQuery.SCHEMAS, _SchemaRow):
        context.db_introspection_result.schema_by_name[schema_row.schema_name] = Schema(
            name=schema_row.schema_name,
            comment=schema_row.schema_comment,
            owner=schema_row.schema_owner,
            grants=frozenset(
                Grant(grantee=grant.grantee, privilege=grant.privilege, grantable=grant.grantable)
                for grant in schema_row.schema_grants
            ),
            table_by_name={},
            sequence_by_name={},
            function_by_signature={},
            enum_by_name={},
            view_by_name={},
            materialized_view_by_name={},
            domain_by_name={},
            composite_type_by_name={},
            range_type_by_name={},
        )
