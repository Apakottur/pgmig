from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, _diff_renamable, _iter_table_pairs
from pgmig._models import DbInfo, Index
from pgmig._sql import comment_on, ident, qualified


def _diff_indexes(
    *, schema_name: str, src: dict[str, Index], dst: dict[str, Index]
) -> tuple[list[str], list[str], list[str]]:
    """
    Diff one table's standalone indexes into (drops, renames, creates), using each
    index's name-independent canonical form as the rename key.
    """
    return _diff_renamable(
        src,
        dst,
        key=lambda index: index.canonical,
        render_drop=lambda name: f"DROP INDEX {qualified(schema_name, name)};",
        render_rename=lambda old, new: f"ALTER INDEX {qualified(schema_name, old)} RENAME TO {ident(new)};",
        render_create=lambda _name, index: f"{index.definition};",
    )


def generate(*, source: DbInfo, target: DbInfo) -> Iterator[Statement]:
    """
    Generate the migration SQL of standalone indexes (create, drop, rename).
    """
    for schema_name, _table_name, src_table, dst_table in _iter_table_pairs(source, target):
        # Table dropped: its indexes are dropped with it.
        if dst_table is None:
            continue

        src_indexes = src_table.index_by_name if src_table else {}
        dst_indexes = dst_table.index_by_name
        drops, renames, creates = _diff_indexes(schema_name=schema_name, src=src_indexes, dst=dst_indexes)
        # Emit drops first (frees names), then renames, then creates.
        for sql in (*drops, *renames, *creates):
            yield Statement(Phase.INDEX, sql)

        # Sync comments for target indexes.
        for index_name, dst_index in dst_indexes.items():
            src_index = src_indexes.get(index_name)
            if (src_index.comment if src_index else None) != dst_index.comment:
                yield Statement(Phase.INDEX, comment_on("INDEX", qualified(schema_name, index_name), dst_index.comment))
