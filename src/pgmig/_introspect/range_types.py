from pgmig._introspect._context import context
from pgmig._introspect._core import _IntrospectionRowWithSchema, run_introspection_query
from pgmig._models import RangeType


class _RangeTypeRow(_IntrospectionRowWithSchema):
    type_name: str
    subtype: str
    subtype_opclass: str | None
    collation: str | None
    subtype_diff: str | None
    type_comment: str | None
    type_owner: str


async def load() -> None:
    """
    Range types (user range types only; extension-owned ones are excluded).
    """
    for row in await run_introspection_query("range_types.sql", _RangeTypeRow):
        context.db_introspection_result.schema_by_name[row.schema_name].range_type_by_name[row.type_name] = RangeType(
            name=row.type_name,
            subtype=row.subtype,
            subtype_opclass=row.subtype_opclass,
            collation=row.collation,
            subtype_diff=row.subtype_diff,
            comment=row.type_comment,
            owner=row.type_owner,
        )
