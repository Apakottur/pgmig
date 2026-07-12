from collections.abc import Iterator

from pgmig._diff._core import Context, Phase, Statement, _iter_schema_pairs
from pgmig._sql import comment_on, ident


def generate(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of schemas.
    """
    for name, src_schema, dst_schema in _iter_schema_pairs(ctx.source, ctx.target):
        # Present in source only: drop it.
        if dst_schema is None:
            yield Statement(Phase.SCHEMA_DROP, f"DROP SCHEMA {ident(name)};")
            continue
        # Present in target only: create it.
        if src_schema is None:
            yield Statement(Phase.SCHEMA_CREATE, f"CREATE SCHEMA {ident(name)};")
        # Sync comment.
        src_comment = src_schema.comment if src_schema else None
        if src_comment != dst_schema.comment:
            yield Statement(Phase.SCHEMA_CREATE, comment_on("SCHEMA", ident(name), dst_schema.comment))
