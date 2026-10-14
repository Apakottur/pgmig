from pgmig._introspect._context import context
from pgmig._introspect._core import Loader
from pgmig._introspect._rows import IntrospectionRowWithSchema
from pgmig._models import Extension


class _ExtensionRow(IntrospectionRowWithSchema):
    name: str
    version: str
    extension_comment: str | None


class ExtensionsLoader(Loader[_ExtensionRow]):
    """
    Extensions (database-level).
    """

    file_name = "extensions.sql"
    model = _ExtensionRow

    def process_rows(self, rows: list[_ExtensionRow]) -> None:
        for ext_row in rows:
            context().db_introspection_result.extension_by_name[ext_row.name] = Extension(
                name=ext_row.name,
                version=ext_row.version,
                schema=ext_row.schema_name,
                comment=ext_row.extension_comment,
            )
