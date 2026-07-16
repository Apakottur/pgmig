from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._models import Domain


class _DomainRow(_QueryRow):
    schema_name: str
    domain_name: str
    data_type: str
    not_null: bool
    default_expr: str | None
    comment: str | None
    checks: dict[str, str]


async def load() -> None:
    """
    Domain types (user domains only; extension-owned ones are excluded).
    """
    for domain_row in await run_introspection_query("domains.sql", _DomainRow):
        context.db_introspection_result.schema_by_name[domain_row.schema_name].domain_by_name[
            domain_row.domain_name
        ] = Domain(
            name=domain_row.domain_name,
            data_type=domain_row.data_type,
            default=domain_row.default_expr,
            not_null=domain_row.not_null,
            check_by_name=domain_row.checks,
            comment=domain_row.comment,
        )
