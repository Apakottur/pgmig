from collections.abc import Iterator

from pgmig._diff._core import (
    Phase,
    RenameDiff,
    Statement,
    ctx_iter_table_pairs,
    diff_child_comment_statements,
    diff_renamable,
)
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
    (pg_trigger.tgenabled) must change, given what the structural diff already does.

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
    Diff one table's triggers into a RenameDiff, using each trigger's name-independent
    canonical form as the rename key.
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


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of triggers. Drops are phased before the functions they
    call are dropped; creates (with renames) after those functions and tables exist.
    """
    for schema_name, table_name, src_table, dst_table in ctx_iter_table_pairs():
        # Table dropped: its triggers are dropped with it.
        if dst_table is None:
            continue

        src_triggers = src_table.trigger_by_name if src_table else {}
        dst_triggers = dst_table.trigger_by_name
        drops, renames, creates, recreated, renamed_from = _diff_triggers(
            schema_name=schema_name,
            table_name=table_name,
            src=src_triggers,
            dst=dst_triggers,
        )
        for sql in drops:
            yield Statement(Phase.TRIGGER_DROP, sql)
        # Renames carry no function dependency, so they ride with the creates. Comments
        # follow, after the triggers they annotate exist.
        comments = diff_child_comment_statements(
            schema_name,
            table_name,
            src_triggers,
            dst_triggers,
            kind="TRIGGER",
            recreated=recreated,
            renamed_from=renamed_from,
        )
        # State fixups ride after the creates: a recreate lands the default state, so a
        # non-default target needs a following ALTER TABLE ... TRIGGER to converge.
        states = _diff_trigger_states(
            table=qualified(schema_name, table_name),
            src=src_triggers,
            dst=dst_triggers,
            recreated=recreated,
            renamed_from=renamed_from,
        )
        for sql in (*renames, *creates, *comments, *states):
            yield Statement(Phase.TRIGGER_CREATE, sql)
