
import asyncpg
from pydantic import BaseModel

from pgmig._build._core import _run_query
from pgmig._models import DbInfo, Function


class _FunctionRow(BaseModel):
    schema_name: str
    func_name: str
    func_args: str
    func_def: str
    func_rettype: str
    func_kind: str
    func_comment: str | None
    func_has_dependents: bool


async def load(conn: asyncpg.Connection, db_info: DbInfo) -> None:
    """
    Functions and procedures (excluding aggregates, window functions, and extension-owned ones).
    """
    for func_row in await _run_query(conn, "functions.sql", _FunctionRow):
        signature = f"{func_row.func_name}({func_row.func_args})"
        db_info.schema_by_name[func_row.schema_name].function_by_signature[signature] = Function(
            name=func_row.func_name,
            identity_arguments=func_row.func_args,
            definition=func_row.func_def.rstrip(),
            return_type=func_row.func_rettype,
            kind=func_row.func_kind,
            comment=func_row.func_comment,
            has_dependents=func_row.func_has_dependents,
        )
