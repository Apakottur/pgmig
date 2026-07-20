from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, _IntrospectionRowWithSchema, run_introspection_query
from pgmig._models import Extension


class _ExtensionRow(_IntrospectionRowWithSchema):
    name: str
    version: str
    extension_comment: str | None


async def load() -> None:
    """
    Extensions (database-level).
    """
    for ext_row in await run_introspection_query(IntrospectionQuery.EXTENSIONS, _ExtensionRow):
        context.db_introspection_result.extension_by_name[ext_row.name] = Extension(
            name=ext_row.name,
            version=ext_row.version,
            schema=ext_row.schema_name,
            comment=ext_row.extension_comment,
        )
