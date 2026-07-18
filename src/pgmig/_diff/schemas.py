from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, ctx_iter_schema_pairs, diff_single_comment, owner_statements
from pgmig._diff.grants import grant_statements
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
        # Sync ownership when the schema exists on both sides (a created schema reconciles later).
        for sql in owner_statements(
            "SCHEMA", ident(name), None if src_schema is None else src_schema.owner, dst_schema.owner
        ):
            yield Statement(Phase.SCHEMA_CREATE, sql)
        # Sync the ACL when the schema exists on both sides (a created schema, like owner,
        # reconciles on a later run). Runs in the GRANT phase, after every create.
        if src_schema is not None:
            for sql in grant_statements(
                "SCHEMA",
                ident(name),
                src_schema.grants,
                dst_schema.grants,
                src_schema.owner,
                dst_schema.owner,
                include_named_roles=context.include_grants,
            ):
                yield Statement(Phase.GRANT, sql)
        # Sync comment.
        for sql in diff_single_comment(
            src_schema,
            dst_schema,
            render=lambda schema: comment_on("SCHEMA", ident(schema.name), schema.comment),
        ):
            yield Statement(Phase.SCHEMA_CREATE, sql)
