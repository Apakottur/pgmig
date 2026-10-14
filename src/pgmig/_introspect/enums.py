from pgmig._introspect._context import context
from pgmig._introspect._core import Loader
from pgmig._introspect._rows import IntrospectionRowWithSchema
from pgmig._models import EnumType


class _EnumRow(IntrospectionRowWithSchema):
    enum_name: str
    enum_values: list[str]
    enum_comment: str | None
    enum_owner: str


class EnumsLoader(Loader[_EnumRow]):
    """
    Enum types (user enums only; extension-owned ones are excluded).
    """

    file_name = "enums.sql"
    model = _EnumRow

    @classmethod
    def process_rows(cls, rows: list[_EnumRow]) -> None:
        for enum_row in rows:
            context().db_introspection_result.schema_by_name[enum_row.schema_name].enum_by_name[enum_row.enum_name] = (
                EnumType(
                    name=enum_row.enum_name,
                    values=enum_row.enum_values,
                    comment=enum_row.enum_comment,
                    owner=enum_row.enum_owner,
                )
            )
