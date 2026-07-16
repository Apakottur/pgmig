from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_schema_pairs, diff_single_comment
from pgmig._sql import comment_on, ident


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of schemas.
    """
    for name, src_schema, dst_schema in ctx_iter_schema_pairs():
        # Present in source only: drop it.
        if dst_schema is None:
            yield Statement(Phase.SCHEMA_DROP, f"DROP SCHEMA {ident(name)};")
            continue
        # Present in target only: create it.
        if src_schema is None:
            yield Statement(Phase.SCHEMA_CREATE, f"CREATE SCHEMA {ident(name)};")
        # Sync comment.
        for sql in diff_single_comment(
            src_schema,
            dst_schema,
            render=lambda schema: comment_on("SCHEMA", ident(schema.name), schema.comment),
        ):
            yield Statement(Phase.SCHEMA_CREATE, sql)
