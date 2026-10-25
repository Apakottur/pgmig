from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, diff_comments, diff_renamable, owner_statements
from pgmig._diff.triggers import trigger_state_statements
from pgmig._sql import comment_on, ident


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of event triggers (pg_event_trigger, database-global).

    An event trigger's event, tag filter and function have no ALTER form, so a change to any of
    them drops and recreates it; a trigger whose only change is its name is renamed. Drops are
    phased before the function a trigger calls is dropped, and creates (with renames, comments,
    enable-state fixups and ownership) after that function exists -- the same slots as table
    triggers.
    """
    src = context().source.event_trigger_by_name
    dst = context().target.event_trigger_by_name

    drops, renames, creates, recreated, renamed_from = diff_renamable(
        src,
        dst,
        key=lambda trigger: trigger.canonical,
        render_drop=lambda name: f"DROP EVENT TRIGGER {ident(name)};",
        render_rename=lambda old, new: f"ALTER EVENT TRIGGER {ident(old)} RENAME TO {ident(new)};",
        render_create=lambda _name, trigger: f"{trigger.definition};",
    )
    for sql in drops:
        yield Statement(Phase.TRIGGER_DROP, sql)

    comments = diff_comments(
        src,
        dst,
        render=lambda name, trigger: comment_on("EVENT TRIGGER", ident(name), trigger.comment),
        recreated=recreated,
        renamed_from=renamed_from,
    )
    # A fresh CREATE lands the default (enabled) state; a non-default target state follows it.
    states = trigger_state_statements(
        src=src,
        dst=dst,
        recreated=recreated,
        renamed_from=renamed_from,
        render=lambda name, verb: f"ALTER EVENT TRIGGER {ident(name)} {verb};",
    )
    # A rename preserves the owner, so resolve the source owner through the old name; a created
    # or recreated trigger has none (it is owned by the role running the migration).
    owners = []
    for name in sorted(dst):
        source = None if name in recreated else src.get(renamed_from.get(name, name))
        owners += owner_statements(
            "EVENT TRIGGER", ident(name), source.owner if source is not None else None, dst[name].owner
        )
    for sql in (*renames, *creates, *comments, *states, *owners):
        yield Statement(Phase.TRIGGER_CREATE, sql)
