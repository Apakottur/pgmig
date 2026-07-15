from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, _run_query
from pgmig._models import CompositeField, CompositeType


class _CompositeFieldRow(_QueryRow):
    name: str
    type: str


class _CompositeTypeRow(_QueryRow):
    schema_name: str
    type_name: str
    type_comment: str | None
    fields: list[_CompositeFieldRow]


async def load() -> None:
    """
    Standalone composite types (user types only; extension-owned ones are excluded).
    """
    for row in await _run_query("composite_types.sql", _CompositeTypeRow):
        fields = [CompositeField(name=field.name, type=field.type) for field in row.fields]
        context.db_info.schema_by_name[row.schema_name].composite_type_by_name[row.type_name] = CompositeType(
            name=row.type_name, fields=fields, comment=row.type_comment
        )
