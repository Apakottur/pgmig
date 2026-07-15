from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, _run_query
from pgmig._models import EnumType


class _EnumRow(_QueryRow):
    schema_name: str
    enum_name: str
    enum_values: list[str]
    enum_comment: str | None


async def load() -> None:
    """
    Enum types (user enums only; extension-owned ones are excluded).
    """
    for enum_row in await _run_query("enums.sql", _EnumRow):
        context.db_info.schema_by_name[enum_row.schema_name].enum_by_name[enum_row.enum_name] = EnumType(
            name=enum_row.enum_name, values=enum_row.enum_values, comment=enum_row.enum_comment
        )
