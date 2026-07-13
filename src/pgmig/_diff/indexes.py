from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, _diff_comments, ctx_iter_table_pairs, diff_renamable
from pgmig._models import Index
from pgmig._sql import comment_on, ident, qualified


def _diff_indexes(
    *,
    schema_name: str,
    src: dict[str, Index],
    dst: dict[str, Index],
) -> tuple[list[str], list[str], list[str], set[str]]:
    """
    Diff one table's standalone indexes into (drops, renames, creates), using each
    index's name-independent canonical form as the rename key.
    """
    return diff_renamable(
        src,
        dst,
        key=lambda index: index.canonical,
        render_drop=lambda name: f"DROP INDEX {qualified(schema_name, name)};",
        render_rename=lambda old, new: f"ALTER INDEX {qualified(schema_name, old)} RENAME TO {ident(new)};",
        render_create=lambda _name, index: f"{index.definition};",
    )


def _index_comment_statements(
    schema_name: str,
    src: dict[str, Index],
    dst: dict[str, Index],
    recreated: set[str],
) -> list[str]:
    """
    Emit COMMENT ON INDEX for target indexes whose comment differs from source.
    """
    return _diff_comments(
        src,
        dst,
        render=lambda name, index: comment_on("INDEX", qualified(schema_name, name), index.comment),
        recreated=recreated,
    )


def diff_index_statements(schema_name: str, src: dict[str, Index], dst: dict[str, Index]) -> list[str]:
    """
    Diff one relation's indexes into ordered migration SQL: drops first (frees names),
    then renames, then creates, then comment syncs. Honors context.index_concurrently.
    Shared by the table and materialized-view index generators.
    """
    drops, renames, creates, recreated = _diff_indexes(schema_name=schema_name, src=src, dst=dst)

    if context.index_concurrently:
        drops = [drop.replace(" INDEX ", " INDEX CONCURRENTLY ", 1) for drop in drops]
        creates = [create.replace(" INDEX ", " INDEX CONCURRENTLY ", 1) for create in creates]

    comments = _index_comment_statements(schema_name, src, dst, recreated)
    return [*drops, *renames, *creates, *comments]


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of standalone indexes (create, drop, rename).
    """
    for schema_name, _table_name, src_table, dst_table in ctx_iter_table_pairs():
        # Table dropped: its indexes are dropped with it.
        if dst_table is None:
            continue

        src_indexes = src_table.index_by_name if src_table else {}
        for sql in diff_index_statements(schema_name, src_indexes, dst_table.index_by_name):
            yield Statement(Phase.INDEX, sql)
