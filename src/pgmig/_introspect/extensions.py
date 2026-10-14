from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, run_introspection_query
from pgmig._introspect._rows import IntrospectionRowWithSchema
from pgmig._models import Extension


class _ExtensionRow(IntrospectionRowWithSchema):
    name: str
    version: str
    extension_comment: str | None


def load_rows(rows: list[_ExtensionRow]) -> None:
    """
    Extensions (database-level).
    """
    for ext_row in rows:
        context().db_introspection_result.extension_by_name[ext_row.name] = Extension(
            name=ext_row.name,
            version=ext_row.version,
            schema=ext_row.schema_name,
            comment=ext_row.extension_comment,
        )


async def load() -> None:
    """
    Run the query and load its rows.
    """
    load_rows(await run_introspection_query(IntrospectionQuery.EXTENSIONS, _ExtensionRow))
