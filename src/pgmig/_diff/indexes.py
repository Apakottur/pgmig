from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, ctx_iter_table_pairs, diff_comment_statements, diff_renamable
from pgmig._models import Index
from pgmig._sql import ident, qualified


def _render_create_index(definition: str, *, concurrently: bool) -> str:
    """
    Terminate an index definition, inserting CONCURRENTLY after the INDEX keyword when
    asked. `definition` is opaque pg_get_indexdef output beginning CREATE [UNIQUE] INDEX,
    so the keyword is the one structured anchor to insert at.
    """
    if concurrently:
        head, _, tail = definition.partition("INDEX ")
        definition = f"{head}INDEX CONCURRENTLY {tail}"
    return f"{definition};"


def _diff_indexes(
    *,
    schema_name: str,
    src: dict[str, Index],
    dst: dict[str, Index],
    concurrently: bool,
) -> tuple[list[str], list[str], list[str], set[str]]:
    """
    Diff one table's standalone indexes into (drops, renames, creates), using each
    index's name-independent canonical form as the rename key. Drops and creates carry
    CONCURRENTLY when requested; a rename is ALTER INDEX and cannot be concurrent.
    """
    drop_keyword = "DROP INDEX CONCURRENTLY" if concurrently else "DROP INDEX"
    return diff_renamable(
        src,
        dst,
        key=lambda index: index.canonical,
        render_drop=lambda name: f"{drop_keyword} {qualified(schema_name, name)};",
        render_rename=lambda old, new: f"ALTER INDEX {qualified(schema_name, old)} RENAME TO {ident(new)};",
        render_create=lambda _name, index: _render_create_index(index.definition, concurrently=concurrently),
    )


def diff_index_statements(schema_name: str, src: dict[str, Index], dst: dict[str, Index]) -> list[str]:
    """
    Diff one relation's indexes into ordered migration SQL: drops first (frees names),
    then renames, then creates, then comment syncs. Honors context.index_concurrently.
    Shared by the table and materialized-view index generators.
    """
    drops, renames, creates, recreated = _diff_indexes(
        schema_name=schema_name, src=src, dst=dst, concurrently=context.index_concurrently
    )

    comments = diff_comment_statements(schema_name, src, dst, kind="INDEX", recreated=recreated)
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
