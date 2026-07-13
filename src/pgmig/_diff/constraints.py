from collections.abc import Iterator

from pgmig._diff._core import Context, Phase, Statement, _diff_comments, _diff_renamable, _iter_table_pairs
from pgmig._models import Constraint
from pgmig._sql import comment_on, ident, schema_qualified


def _diff_constraints(
    *, schema_name: str, table_name: str, src: dict[str, Constraint], dst: dict[str, Constraint]
) -> tuple[list[str], list[str], list[str], set[str]]:
    """
    Diff one table's constraints (of a single kind) into (drops, renames, adds).
    The constraint definition (from pg_get_constraintdef) is already name-independent.
    """
    prefix = f"ALTER TABLE {schema_qualified(schema_name, table_name)}"
    return _diff_renamable(
        src,
        dst,
        key=lambda constraint: constraint.definition,
        render_drop=lambda name: f"{prefix} DROP CONSTRAINT {ident(name)};",
        render_rename=lambda old, new: f"{prefix} RENAME CONSTRAINT {ident(old)} TO {ident(new)};",
        render_create=lambda name, constraint: f"{prefix} ADD CONSTRAINT {ident(name)} {constraint.definition};",
    )


def _constraint_comment_statements(
    schema_name: str, table_name: str, src: dict[str, Constraint], dst: dict[str, Constraint], recreated: set[str]
) -> list[str]:
    """
    Emit COMMENT ON CONSTRAINT for target constraints whose comment differs from source.
    """
    table = schema_qualified(schema_name, table_name)
    return _diff_comments(
        src,
        dst,
        render=lambda name, constraint: comment_on("CONSTRAINT", f"{ident(name)} ON {table}", constraint.comment),
        recreated=recreated,
    )


def generate(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of primary key, unique, and check constraints (add, drop, rename).
    """
    for schema_name, table_name, src_table, dst_table in _iter_table_pairs(ctx.source, ctx.target):
        # Table dropped: its constraints are dropped with it.
        if dst_table is None:
            continue

        src_constraints = src_table.constraint_by_name if src_table else {}
        dst_constraints = dst_table.constraint_by_name
        drops, renames, adds, recreated = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_constraints,
            dst=dst_constraints,
        )
        comments = _constraint_comment_statements(schema_name, table_name, src_constraints, dst_constraints, recreated)
        # Drops first (frees names), then renames, then adds, then comments.
        for sql in (*drops, *renames, *adds, *comments):
            yield Statement(Phase.CONSTRAINT, sql)


def generate_foreign_keys(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of foreign key constraints. Drops are phased before
    referenced objects are dropped; adds (with renames) after referenced tables and
    their keys exist.
    """
    for schema_name, table_name, src_table, dst_table in _iter_table_pairs(ctx.source, ctx.target):
        src_fks = src_table.foreign_key_by_name if src_table else {}
        # Table dropped: its foreign keys must still be dropped explicitly, in the
        # FOREIGN_KEY_DROP phase (before any DROP TABLE), so a referenced table can be
        # dropped even while its referencing table's constraint has not yet cascaded away.
        dst_fks = dst_table.foreign_key_by_name if dst_table else {}
        drops, renames, adds, recreated = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_fks,
            dst=dst_fks,
        )
        for sql in drops:
            yield Statement(Phase.FOREIGN_KEY_DROP, sql)
        # Renames carry no referenced-object dependency, so they ride with the adds.
        comments = _constraint_comment_statements(schema_name, table_name, src_fks, dst_fks, recreated)
        for sql in (*renames, *adds, *comments):
            yield Statement(Phase.FOREIGN_KEY_ADD, sql)
