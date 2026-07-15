from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, _run_query
from pgmig._models import Extension


class _ExtensionRow(_QueryRow):
    name: str
    version: str
    extension_schema: str
    extension_comment: str | None


async def load() -> None:
    """
    Extensions (database-level).
    """
    for ext_row in await _run_query("extensions.sql", _ExtensionRow):
        context.db_info.extension_by_name[ext_row.name] = Extension(
            name=ext_row.name,
            version=ext_row.version,
            schema=ext_row.extension_schema,
            comment=ext_row.extension_comment,
        )
