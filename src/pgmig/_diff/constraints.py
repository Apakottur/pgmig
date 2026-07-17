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

# pg_get_constraintdef renders a not-validated check/foreign key with this trailing suffix.
_NOT_VALID_SUFFIX = " NOT VALID"


def _extract_validations(
    prefix: str, src: dict[str, Constraint], dst: dict[str, Constraint]
) -> tuple[dict[str, Constraint], dict[str, Constraint], list[str]]:
    """
    Pull out same-name constraints that only transition NOT VALID -> valid.

    pg_get_constraintdef bakes NOT VALID into the definition, so validating a constraint
    changes its definition string and the generic diff would drop and re-add it -- a full
    re-check under a stronger lock. Instead emit the cheap `VALIDATE CONSTRAINT` and remove
    the pair from the maps so the generic diff leaves it alone. The reverse (valid ->
    NOT VALID) has no ALTER form, so it is left to fall through to drop-and-re-add.
    """
    src = dict(src)
    dst = dict(dst)
    validations: list[str] = []
    for name in sorted(src.keys() & dst.keys()):
        src_def = src[name].definition
        dst_def = dst[name].definition
        if src_def.endswith(_NOT_VALID_SUFFIX) and src_def[: -len(_NOT_VALID_SUFFIX)] == dst_def:
            validations.append(f"{prefix} VALIDATE CONSTRAINT {ident(name)};")
            del src[name]
            del dst[name]
    return src, dst, validations


def _diff_constraints(
    *, schema_name: str, table_name: str, src: dict[str, Constraint], dst: dict[str, Constraint]
) -> tuple[RenameDiff, list[str]]:
    """
    Diff one table's constraints (of a single kind) into a RenameDiff plus the in-place
    `VALIDATE CONSTRAINT` statements for NOT VALID -> valid transitions.
    The constraint definition (from pg_get_constraintdef) is already name-independent.
    """
    prefix = f"ALTER TABLE {qualified(schema_name, table_name)}"
    src, dst, validations = _extract_validations(prefix, src, dst)
    diff = diff_renamable(
        src,
        dst,
        key=lambda constraint: constraint.definition,
        render_drop=lambda name: f"{prefix} DROP CONSTRAINT {ident(name)};",
        render_rename=lambda old, new: f"{prefix} RENAME CONSTRAINT {ident(old)} TO {ident(new)};",
        render_create=lambda name, constraint: f"{prefix} ADD CONSTRAINT {ident(name)} {constraint.definition};",
    )
    return diff, validations


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
        (drops, renames, adds, recreated, renamed_from), validations = _diff_constraints(
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
        # Drops first (frees names), then renames, then adds, then validations, then comments.
        for sql in (*drops, *renames, *adds, *validations, *comments):
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
        (drops, renames, adds, recreated, renamed_from), validations = _diff_constraints(
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
        # Validations only touch the existing constraint's own rows, so they ride with the adds.
        for sql in (*renames, *adds, *validations, *comments):
            yield Statement(Phase.FOREIGN_KEY_ADD, sql)
