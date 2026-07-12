from collections.abc import Iterator

from pgmig._diff._core import Context, Phase, Statement, _diff_comments, _diff_renamable, _iter_table_pairs
from pgmig._models import Trigger
from pgmig._sql import comment_on, ident, qualified


def _diff_triggers(
    *, schema_name: str, table_name: str, src: dict[str, Trigger], dst: dict[str, Trigger]
) -> tuple[list[str], list[str], list[str], set[str]]:
    """
    Diff one table's triggers into (drops, renames, creates), using each trigger's
    name-independent canonical form as the rename key.
    """
    table = qualified(schema_name, table_name)
    return _diff_renamable(
        src,
        dst,
        key=lambda trigger: trigger.canonical,
        render_drop=lambda name: f"DROP TRIGGER {ident(name)} ON {table};",
        render_rename=lambda old, new: f"ALTER TRIGGER {ident(old)} ON {table} RENAME TO {ident(new)};",
        render_create=lambda _name, trigger: f"{trigger.definition};",
    )


def _trigger_comment_statements(
    schema_name: str, table_name: str, src: dict[str, Trigger], dst: dict[str, Trigger], recreated: set[str]
) -> list[str]:
    """
    Emit COMMENT ON TRIGGER for target triggers whose comment differs from source.
    """
    table = qualified(schema_name, table_name)
    return _diff_comments(
        src,
        dst,
        render=lambda name, trigger: comment_on("TRIGGER", f"{ident(name)} ON {table}", trigger.comment),
        recreated=recreated,
    )


def generate(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of triggers. Drops are phased before the functions they
    call are dropped; creates (with renames) after those functions and tables exist.
    """
    for schema_name, table_name, src_table, dst_table in _iter_table_pairs(ctx.source, ctx.target):
        # Table dropped: its triggers are dropped with it.
        if dst_table is None:
            continue

        src_triggers = src_table.trigger_by_name if src_table else {}
        dst_triggers = dst_table.trigger_by_name
        drops, renames, creates, recreated = _diff_triggers(
            schema_name=schema_name, table_name=table_name, src=src_triggers, dst=dst_triggers
        )
        for sql in drops:
            yield Statement(Phase.TRIGGER_DROP, sql)
        # Renames carry no function dependency, so they ride with the creates. Comments
        # follow, after the triggers they annotate exist.
        comments = _trigger_comment_statements(schema_name, table_name, src_triggers, dst_triggers, recreated)
        for sql in (*renames, *creates, *comments):
            yield Statement(Phase.TRIGGER_CREATE, sql)
