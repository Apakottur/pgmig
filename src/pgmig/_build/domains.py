from typing import Any

import psycopg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo, Domain


class _DomainRow(BaseModel):
    schema_name: str
    domain_name: str
    data_type: str
    not_null: bool
    default_expr: str | None
    comment: str | None
    checks: dict[str, str]


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Domain types (user domains only; extension-owned ones are excluded).
    """
    for domain_row in _run_query(conn, "domains.sql", _DomainRow):
        db_info.schema_by_name[domain_row.schema_name].domain_by_name[domain_row.domain_name] = Domain(
            name=domain_row.domain_name,
            data_type=domain_row.data_type,
            default=domain_row.default_expr,
            not_null=domain_row.not_null,
            check_by_name=domain_row.checks,
            comment=domain_row.comment,
        )
