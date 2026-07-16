from collections.abc import Iterator

from pgmig._diff._core import (
    Phase,
    RenameDiff,
    Statement,
    ctx_iter_table_pairs,
    diff_child_comment_statements,
    diff_renamable,
)
from pgmig._models import Constraint
from pgmig._sql import ident, qualified


def _diff_constraints(
    *, schema_name: str, table_name: str, src: dict[str, Constraint], dst: dict[str, Constraint]
) -> RenameDiff:
    """
    Diff one table's constraints (of a single kind) into a RenameDiff.
    The constraint definition (from pg_get_constraintdef) is already name-independent.
    """
    prefix = f"ALTER TABLE {qualified(schema_name, table_name)}"
    return diff_renamable(
        src,
        dst,
        key=lambda constraint: constraint.definition,
        render_drop=lambda name: f"{prefix} DROP CONSTRAINT {ident(name)};",
        render_rename=lambda old, new: f"{prefix} RENAME CONSTRAINT {ident(old)} TO {ident(new)};",
        render_create=lambda name, constraint: f"{prefix} ADD CONSTRAINT {ident(name)} {constraint.definition};",
    )


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of primary key, unique, check, and exclusion constraints
    (add, drop, rename).
    """
    for schema_name, table_name, src_table, dst_table in ctx_iter_table_pairs():
        # Table dropped: its constraints are dropped with it.
        if dst_table is None:
            continue

        src_constraints = src_table.constraint_by_name if src_table else {}
        dst_constraints = dst_table.constraint_by_name
        drops, renames, adds, recreated, renamed_from = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_constraints,
            dst=dst_constraints,
        )
        comments = diff_child_comment_statements(
            schema_name,
            table_name,
            src_constraints,
            dst_constraints,
            kind="CONSTRAINT",
            recreated=recreated,
            renamed_from=renamed_from,
        )
        # Drops first (frees names), then renames, then adds, then comments.
        for sql in (*drops, *renames, *adds, *comments):
            yield Statement(Phase.CONSTRAINT, sql)


def generate_foreign_keys() -> Iterator[Statement]:
    """
    Generate the migration SQL of foreign key constraints. Drops are phased before
    referenced objects are dropped; adds (with renames) after referenced tables and
    their keys exist.
    """
    for schema_name, table_name, src_table, dst_table in ctx_iter_table_pairs():
        src_fks = src_table.foreign_key_by_name if src_table else {}
        # Table dropped: its foreign keys must still be dropped explicitly, in the
        # FOREIGN_KEY_DROP phase (before any DROP TABLE), so a referenced table can be
        # dropped even while its referencing table's constraint has not yet cascaded away.
        dst_fks = dst_table.foreign_key_by_name if dst_table else {}
        drops, renames, adds, recreated, renamed_from = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_fks,
            dst=dst_fks,
        )
        for sql in drops:
            yield Statement(Phase.FOREIGN_KEY_DROP, sql)
        # Renames carry no referenced-object dependency, so they ride with the adds.
        comments = diff_child_comment_statements(
            schema_name, table_name, src_fks, dst_fks, kind="CONSTRAINT", recreated=recreated, renamed_from=renamed_from
        )
        for sql in (*renames, *adds, *comments):
            yield Statement(Phase.FOREIGN_KEY_ADD, sql)
