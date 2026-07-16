from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._models import Constraint


class _ConstraintRow(_QueryRow):
    schema_name: str
    table_name: str
    con_name: str
    con_def: str
    con_type: str
    con_columns: list[str] | None
    con_comment: str | None


async def load() -> None:
    """
    Constraints (primary key, unique, check, and exclusion). Foreign keys are routed to their
    own bucket on the table.
    """
    for con_row in await run_introspection_query("constraints.sql", _ConstraintRow):
        constraint = Constraint(
            name=con_row.con_name,
            definition=con_row.con_def,
            contype=con_row.con_type,
            columns=con_row.con_columns or [],
            comment=con_row.con_comment,
        )
        table = context.db_introspection_result.schema_by_name[con_row.schema_name].table_by_name[con_row.table_name]
        if constraint.is_foreign_key:
            table.foreign_key_by_name[con_row.con_name] = constraint
        else:
            table.constraint_by_name[con_row.con_name] = constraint
