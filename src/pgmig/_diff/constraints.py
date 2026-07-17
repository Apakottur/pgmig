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


def _base_definition(constraint: Constraint) -> str:
    """
    The pg_get_constraintdef output with its trailing deferrability clause removed, so two
    constraints that differ only in DEFERRABLE / INITIALLY DEFERRED compare equal. The suffix
    is deterministic: " DEFERRABLE INITIALLY DEFERRED" when deferred, " DEFERRABLE" when merely
    deferrable, nothing otherwise.
    """
    if constraint.deferred:
        return constraint.definition.removesuffix(" DEFERRABLE INITIALLY DEFERRED")
    if constraint.deferrable:
        return constraint.definition.removesuffix(" DEFERRABLE")
    return constraint.definition


def _deferrability_clause(constraint: Constraint) -> str:
    """
    The ALTER CONSTRAINT deferrability spelling for a constraint's target state, always fully
    stated so the change converges regardless of the source state.
    """
    if not constraint.deferrable:
        return "NOT DEFERRABLE"
    return "DEFERRABLE INITIALLY DEFERRED" if constraint.deferred else "DEFERRABLE INITIALLY IMMEDIATE"


def _diff_constraints(
    *, schema_name: str, table_name: str, src: dict[str, Constraint], dst: dict[str, Constraint]
) -> tuple[list[str], RenameDiff]:
    """
    Diff one table's constraints (of a single kind) into (deferrability-only alters, RenameDiff).

    A same-name constraint that differs only in its deferrability rides in the
    pg_get_constraintdef string, so the plain key comparison would see it as a changed
    definition and drop + re-add it -- rebuilding the backing index for unique/primary-key
    constraints. Foreign keys instead take an ALTER TABLE ... ALTER CONSTRAINT, the only kind
    Postgres lets change deferrability in place on the supported versions (14-18); the matched
    pair is then removed so the RenameDiff treats it as a no-op. Every other kind (unique,
    primary key, check, exclusion) falls through to the ordinary drop + re-add.
    """
    prefix = f"ALTER TABLE {qualified(schema_name, table_name)}"
    src = dict(src)
    dst = dict(dst)
    alters: list[str] = []
    for name in sorted(src.keys() & dst.keys()):
        src_con, dst_con = src[name], dst[name]
        if (
            dst_con.is_foreign_key
            and src_con.definition != dst_con.definition
            and _base_definition(src_con) == _base_definition(dst_con)
        ):
            alters.append(f"{prefix} ALTER CONSTRAINT {ident(name)} {_deferrability_clause(dst_con)};")
            del src[name]
            del dst[name]

    diff = diff_renamable(
        src,
        dst,
        key=lambda constraint: constraint.definition,
        render_drop=lambda name: f"{prefix} DROP CONSTRAINT {ident(name)};",
        render_rename=lambda old, new: f"{prefix} RENAME CONSTRAINT {ident(old)} TO {ident(new)};",
        render_create=lambda name, constraint: f"{prefix} ADD CONSTRAINT {ident(name)} {constraint.definition};",
    )
    return alters, diff


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
        alters, (drops, renames, adds, recreated, renamed_from) = _diff_constraints(
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
        # `alters` (deferrability-only ALTER CONSTRAINT) is always empty here: no non-foreign-key
        # constraint kind supports an in-place deferrability change, so those fall through to the
        # drop + re-add above. Kept in the sequence for the uniform signature.
        # Drops first (frees names), then renames, then adds, then comments.
        for sql in (*drops, *renames, *adds, *alters, *comments):
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
        alters, (drops, renames, adds, recreated, renamed_from) = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_fks,
            dst=dst_fks,
        )
        for sql in drops:
            yield Statement(Phase.FOREIGN_KEY_DROP, sql)
        # Renames and deferrability-only ALTER CONSTRAINTs carry no referenced-object
        # dependency, so they ride with the adds.
        comments = diff_child_comment_statements(
            schema_name, table_name, src_fks, dst_fks, kind="CONSTRAINT", recreated=recreated, renamed_from=renamed_from
        )
        for sql in (*renames, *alters, *adds, *comments):
            yield Statement(Phase.FOREIGN_KEY_ADD, sql)
