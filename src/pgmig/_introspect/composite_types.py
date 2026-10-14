from pgmig._introspect._context import context
from pgmig._introspect._rows import IntrospectionRow, IntrospectionRowWithSchema
from pgmig._models import CompositeField, CompositeType


class _CompositeFieldRow(IntrospectionRow):
    name: str
    type: str


class CompositeTypeRow(IntrospectionRowWithSchema):
    type_name: str
    type_comment: str | None
    type_owner: str
    fields: list[_CompositeFieldRow]


def load_rows(rows: list[CompositeTypeRow]) -> None:
    """
    Standalone composite types (user types only; extension-owned ones are excluded).
    """
    for row in rows:
        fields = [CompositeField(name=field.name, type=field.type) for field in row.fields]
        context().db_introspection_result.schema_by_name[row.schema_name].composite_type_by_name[row.type_name] = (
            CompositeType(name=row.type_name, fields=fields, comment=row.type_comment, owner=row.type_owner)
        )
