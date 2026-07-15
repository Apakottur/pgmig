from typing import Any

import psycopg

from pgmig._introspect._core import _QueryRow, _run_query
from pgmig._models import DbInfo, Trigger


class _TriggerRow(_QueryRow):
    schema_name: str
    table_name: str
    trigger_name: str
    trigger_def: str
    trigger_canonical: str
    trigger_comment: str | None


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Triggers (user triggers only; internal RI/constraint-backing triggers are excluded).
    """
    for trigger_row in _run_query(conn, "triggers.sql", _TriggerRow):
        table = db_info.schema_by_name[trigger_row.schema_name].table_by_name[trigger_row.table_name]
        table.trigger_by_name[trigger_row.trigger_name] = Trigger(
            name=trigger_row.trigger_name,
            definition=trigger_row.trigger_def,
            canonical=trigger_row.trigger_canonical,
            comment=trigger_row.trigger_comment,
        )
