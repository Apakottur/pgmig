from pgmig._introspect._context import context
from pgmig._introspect._core import _IntrospectionRowWithSchema, run_introspection_query
from pgmig._models import Table, Trigger, View


class _TriggerRow(_IntrospectionRowWithSchema):
    table_name: str
    relkind: str  # pg_class.relkind of the owning relation: 'r'/'p' table, 'v' view
    trigger_name: str
    trigger_def: str
    trigger_canonical: str
    trigger_enabled: str
    trigger_comment: str | None


async def load() -> None:
    """
    Triggers (user triggers only; internal RI/constraint-backing triggers are excluded).

    A trigger's owner is a table ('r'/'p') or, for INSTEAD OF triggers, a view ('v'); route the
    row to the matching mapping so both carry their triggers uniformly. This runs after both
    tables and views are loaded so both lookups resolve.
    """
    for trigger_row in await run_introspection_query("triggers.sql", _TriggerRow):
        schema = context.db_introspection_result.schema_by_name[trigger_row.schema_name]
        owner: Table | View
        if trigger_row.relkind == "v":
            owner = schema.view_by_name[trigger_row.table_name]
        else:
            owner = schema.table_by_name[trigger_row.table_name]
        owner.trigger_by_name[trigger_row.trigger_name] = Trigger(
            name=trigger_row.trigger_name,
            definition=trigger_row.trigger_def,
            canonical=trigger_row.trigger_canonical,
            enabled=trigger_row.trigger_enabled,
            comment=trigger_row.trigger_comment,
        )
