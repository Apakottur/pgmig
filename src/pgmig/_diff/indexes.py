from collections.abc import Callable, Iterator

from pgmig._diff._core import Context, Phase, Statement, _diff_comments, _diff_renamable, _iter_table_pairs
from pgmig._models import Index
from pgmig._sql import comment_on, ident, qualified


def _concurrently(definition: str) -> str:
    """
    Insert CONCURRENTLY into a `CREATE [UNIQUE] INDEX ...` statement (from
    pg_get_indexdef), right after the INDEX keyword. pg_get_indexdef always begins with
    `CREATE INDEX` or `CREATE UNIQUE INDEX`, so replacing the first ` INDEX ` covers both.
    """
    return definition.replace(" INDEX ", " INDEX CONCURRENTLY ", 1)


def _diff_indexes(
    *,
    schema_name: str,
    src: dict[str, Index],
    dst: dict[str, Index],
    concurrently: bool,
) -> tuple[list[str], list[str], list[str], set[str]]:
    """
    Diff one table's standalone indexes into (drops, renames, creates), using each
    index's name-independent canonical form as the rename key. When `concurrently`,
    creates and drops carry CONCURRENTLY (a rename cannot and never does).
    """
    drop_keyword = "DROP INDEX CONCURRENTLY" if concurrently else "DROP INDEX"
    render_create: Callable[[str, Index], str] = (
        (lambda _name, index: f"{_concurrently(index.definition)};")
        if concurrently
        else (lambda _name, index: f"{index.definition};")
    )
    return _diff_renamable(
        src,
        dst,
        key=lambda index: index.canonical,
        render_drop=lambda name: f"{drop_keyword} {qualified(schema_name, name)};",
        render_rename=lambda old, new: f"ALTER INDEX {qualified(schema_name, old)} RENAME TO {ident(new)};",
        render_create=render_create,
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


def generate(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of standalone indexes (create, drop, rename).
    """
    for schema_name, _table_name, src_table, dst_table in _iter_table_pairs(ctx.source, ctx.target):
        # Table dropped: its indexes are dropped with it.
        if dst_table is None:
            continue

        src_indexes = src_table.index_by_name if src_table else {}
        dst_indexes = dst_table.index_by_name
        drops, renames, creates, recreated = _diff_indexes(
            schema_name=schema_name,
            src=src_indexes,
            dst=dst_indexes,
            concurrently=ctx.options.index_concurrently,
        )
        comments = _index_comment_statements(schema_name, src_indexes, dst_indexes, recreated)
        # Emit drops first (frees names), then renames, then creates, then comments.
        for sql in (*drops, *renames, *creates, *comments):
            yield Statement(Phase.INDEX, sql)
