from pgmig._introspect._context import context
from pgmig._introspect._rows import IntrospectionRowWithSchema
from pgmig._models import RangeType


class RangeTypeRow(IntrospectionRowWithSchema):
    type_name: str
    subtype: str
    subtype_opclass: str | None
    collation: str | None
    subtype_diff: str | None
    type_comment: str | None
    type_owner: str


def load_rows(rows: list[RangeTypeRow]) -> None:
    """
    Range types (user range types only; extension-owned ones are excluded).
    """
    for row in rows:
        context().db_introspection_result.schema_by_name[row.schema_name].range_type_by_name[row.type_name] = RangeType(
            name=row.type_name,
            subtype=row.subtype,
            subtype_opclass=row.subtype_opclass,
            collation=row.collation,
            subtype_diff=row.subtype_diff,
            comment=row.type_comment,
            owner=row.type_owner,
        )
