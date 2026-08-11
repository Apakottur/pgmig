from collections.abc import Iterator

from pgmig._diff._core import (
    Phase,
    RenameDiff,
    Statement,
    ctx_iter_table_pairs,
    ctx_iter_view_pairs,
    diff_child_comment_statements,
    diff_renamable,
    recreated_view_keys,
)
from pgmig._keys import RelationKey
from pgmig._models import Trigger
from pgmig._sql import ident, qualified

# pg_trigger.tgenabled: the state a freshly CREATE'd trigger always has (origin/default).
_DEFAULT_ENABLED = "O"
# tgenabled code -> the ALTER TABLE ... TRIGGER verb that sets that state.
_ENABLED_VERB = {
    "O": "ENABLE",
    "D": "DISABLE",
    "R": "ENABLE REPLICA",
    "A": "ENABLE ALWAYS",
}


def _diff_trigger_states(
    *,
    table: str,
    src: dict[str, Trigger],
    dst: dict[str, Trigger],
    recreated: set[str],
    renamed_from: dict[str, str],
) -> list[str]:
    """
    Emit ALTER TABLE ... {ENABLE | DISABLE | ...} TRIGGER for triggers whose enable state
    (pg_trigger.tgenabled) must change, given what the structural diff already does. A view's
    INSTEAD OF trigger cannot be disabled (Postgres refuses ALTER TABLE ... DISABLE TRIGGER on
    a view), so its state is always the default and this is a no-op there -- but the shared
    call keeps the table and view walks uniform.

    The state a target trigger carries *after* the structural statements run is:
      - default (a fresh CREATE) if it was recreated (dropped and recreated for a definition
        change, or a create reusing a rename-vacated name) or is a brand-new create;
      - its source state otherwise, since a RENAME and an untouched trigger both preserve it.
    A statement is emitted only where that carried-over state differs from the target's.
    """
    statements = []
    for name in sorted(dst):
        target = dst[name].enabled
        if name in recreated or (name not in src and name not in renamed_from):
            current = _DEFAULT_ENABLED
        elif name in renamed_from:
            current = src[renamed_from[name]].enabled
        else:
            current = src[name].enabled
        if current != target:
            statements.append(f"ALTER TABLE {table} {_ENABLED_VERB[target]} TRIGGER {ident(name)};")
    return statements


def _diff_triggers(
    *,
    schema_name: str,
    table_name: str,
    src: dict[str, Trigger],
    dst: dict[str, Trigger],
) -> RenameDiff:
    """
    Diff one relation's triggers into a RenameDiff, using each trigger's name-independent
    canonical form as the rename key. The relation is a table or a view (INSTEAD OF triggers);
    the rendered DROP/ALTER/CREATE TRIGGER ... ON <relation> is identical for both.
    """
    table = qualified(schema_name, table_name)
    return diff_renamable(
        src,
        dst,
        key=lambda trigger: trigger.canonical,
        render_drop=lambda name: f"DROP TRIGGER {ident(name)} ON {table};",
        render_rename=lambda old, new: f"ALTER TRIGGER {ident(old)} ON {table} RENAME TO {ident(new)};",
        render_create=lambda _name, trigger: f"{trigger.definition};",
    )


def _emit_relation_triggers(
    schema_name: str, relation_name: str, src: dict[str, Trigger], dst: dict[str, Trigger]
) -> Iterator[Statement]:
    """
    Diff and emit one relation's triggers: drops in TRIGGER_DROP, then renames + creates +
    comments + enable-state fixups in TRIGGER_CREATE. Shared by the table and view walks.
    """
    drops, renames, creates, recreated, renamed_from = _diff_triggers(
        schema_name=schema_name, table_name=relation_name, src=src, dst=dst
    )
    for sql in drops:
        yield Statement(Phase.TRIGGER_DROP, sql)
    # Renames carry no function dependency, so they ride with the creates. Comments
    # follow, after the triggers they annotate exist.
    comments = diff_child_comment_statements(
        schema_name,
        relation_name,
        src,
        dst,
        kind="TRIGGER",
        recreated=recreated,
        renamed_from=renamed_from,
    )
    # State fixups ride after the creates: a recreate lands the default state, so a
    # non-default target needs a following ALTER TABLE ... TRIGGER to converge.
    states = _diff_trigger_states(
        table=qualified(schema_name, relation_name),
        src=src,
        dst=dst,
        recreated=recreated,
        renamed_from=renamed_from,
    )
    for sql in (*renames, *creates, *comments, *states):
        yield Statement(Phase.TRIGGER_CREATE, sql)


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of triggers, for tables and for views (INSTEAD OF triggers).
    Drops are phased before the functions they call are dropped; creates (with renames) after
    those functions and their tables/views exist.
    """
    for schema_name, table_name, src_table, dst_table in ctx_iter_table_pairs():
        # Table dropped: its triggers are dropped with it.
        if dst_table is None:
            continue
        src_triggers = src_table.trigger_by_name if src_table else {}
        yield from _emit_relation_triggers(schema_name, table_name, src_triggers, dst_table.trigger_by_name)

    # A view whose definition or options changed is dropped and recreated (see views.py), and
    # DROP VIEW silently takes its triggers with it. So a recreated view's source triggers must
    # be treated as absent: every target trigger is re-created after VIEW_CREATE (landing the
    # default enable state, which the state fixup then corrects), and no DROP TRIGGER is emitted
    # against the view that no longer exists.
    recreate = recreated_view_keys()
    for schema_name, view_name, src_view, dst_view in ctx_iter_view_pairs():
        # View dropped: its triggers are dropped with it.
        if dst_view is None:
            continue
        if RelationKey(schema_name, view_name) in recreate:
            src_triggers = {}
        else:
            src_triggers = src_view.trigger_by_name if src_view else {}
        yield from _emit_relation_triggers(schema_name, view_name, src_triggers, dst_view.trigger_by_name)
