from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._models import Trigger


class _TriggerRow(_QueryRow):
    schema_name: str
    table_name: str
    trigger_name: str
    trigger_def: str
    trigger_canonical: str
    trigger_comment: str | None


async def load() -> None:
    """
    Triggers (user triggers only; internal RI/constraint-backing triggers are excluded).
    """
    for trigger_row in await run_introspection_query("triggers.sql", _TriggerRow):
        table = context.db_introspection_result.schema_by_name[trigger_row.schema_name].table_by_name[
            trigger_row.table_name
        ]
        table.trigger_by_name[trigger_row.trigger_name] = Trigger(
            name=trigger_row.trigger_name,
            definition=trigger_row.trigger_def,
            canonical=trigger_row.trigger_canonical,
            comment=trigger_row.trigger_comment,
        )
