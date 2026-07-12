from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, _diff_renamable, _iter_table_pairs
from pgmig._models import DbInfo, Trigger
from pgmig._sql import ident, qualified


def _diff_triggers(
    *, schema_name: str, table_name: str, src: dict[str, Trigger], dst: dict[str, Trigger]
) -> tuple[list[str], list[str], list[str]]:
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


def generate(*, source: DbInfo, target: DbInfo) -> Iterator[Statement]:
    """
    Generate the migration SQL of triggers. Drops are phased before the functions they
    call are dropped; creates (with renames) after those functions and tables exist.
    """
    for schema_name, table_name, src_table, dst_table in _iter_table_pairs(source, target):
        # Table dropped: its triggers are dropped with it.
        if dst_table is None:
            continue

        src_triggers = src_table.trigger_by_name if src_table else {}
        drops, renames, creates = _diff_triggers(
            schema_name=schema_name, table_name=table_name, src=src_triggers, dst=dst_table.trigger_by_name
        )
        for sql in drops:
            yield Statement(Phase.TRIGGER_DROP, sql)
        # Renames carry no function dependency, so they ride with the creates.
        for sql in (*renames, *creates):
            yield Statement(Phase.TRIGGER_CREATE, sql)
