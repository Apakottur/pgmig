from pgmig._introspect._context import context
from pgmig._introspect._core import Loader
from pgmig._introspect._rows import IntrospectionRow
from pgmig._models import EventTrigger


class _EventTriggerRow(IntrospectionRow):
    trigger_name: str
    event: str
    tags: list[str]
    function_schema: str
    function_name: str
    enabled: str
    owner: str
    comment: str | None


class EventTriggersLoader(Loader[_EventTriggerRow]):
    """
    Event triggers (pg_event_trigger, database-level).
    """

    file_name = "event_triggers.sql"
    model = _EventTriggerRow

    @classmethod
    def process_rows(cls, rows: list[_EventTriggerRow]) -> None:
        for row in rows:
            # An event trigger has no schema, so the row is not an IntrospectionRowWithSchema and
            # run_introspection_query does not drop it; skip a trigger whose function sits in an
            # ignored schema, since the trigger cannot exist without its function.
            if row.function_schema in context().ignore_schemas:
                continue
            context().db_introspection_result.event_trigger_by_name[row.trigger_name] = EventTrigger(
                name=row.trigger_name,
                event=row.event,
                tags=tuple(row.tags),
                function_schema=row.function_schema,
                function_name=row.function_name,
                enabled=row.enabled,
                owner=row.owner,
                comment=row.comment,
            )
