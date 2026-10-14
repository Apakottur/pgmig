from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, run_introspection_query
from pgmig._introspect._rows import IntrospectionRowWithSchema
from pgmig._models import EnumType


class _EnumRow(IntrospectionRowWithSchema):
    enum_name: str
    enum_values: list[str]
    enum_comment: str | None
    enum_owner: str


def load_rows(rows: list[_EnumRow]) -> None:
    """
    Enum types (user enums only; extension-owned ones are excluded).
    """
    for enum_row in rows:
        context().db_introspection_result.schema_by_name[enum_row.schema_name].enum_by_name[enum_row.enum_name] = (
            EnumType(
                name=enum_row.enum_name,
                values=enum_row.enum_values,
                comment=enum_row.enum_comment,
                owner=enum_row.enum_owner,
            )
        )


async def load() -> None:
    """
    Run the query and load its rows.
    """
    load_rows(await run_introspection_query(IntrospectionQuery.ENUMS, _EnumRow))
