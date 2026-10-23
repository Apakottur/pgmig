from collections.abc import Callable, Iterator

from pgmig._diff._core import (
    Phase,
    RenameDiff,
    Statement,
    ctx_iter_table_pairs,
    diff_child_comment_statements,
    diff_renamable,
    removed_columns,
    without_column_removal_cascades,
)
from pgmig._models import Constraint
from pgmig._sql import ident, qualified

# pg_get_constraintdef renders a not-validated check/foreign key with this trailing suffix.
_NOT_VALID_SUFFIX = " NOT VALID"
# pg_get_constraintdef (Postgres 18+) appends this marker for a NOT ENFORCED constraint; an
# enforced constraint (the default) carries no such suffix. Two definitions equal once it is
# stripped differ only in their enforced state. Postgres emits at most one of NOT ENFORCED /
# NOT VALID (NOT ENFORCED implies NOT VALID, and only the former is shown), so the enforcement
# and validation extractions below never race for the same constraint.
_NOT_ENFORCED_SUFFIX = " NOT ENFORCED"


def _extract(
    prefix: str,
    src: dict[str, Constraint],
    dst: dict[str, Constraint],
    render: Callable[[str, str, Constraint, Constraint], str | None],
) -> tuple[dict[str, Constraint], dict[str, Constraint], list[str]]:
    """
    Pull out the same-name constraint pairs `render` turns into an in-place ALTER, removing each
    from (copies of) the maps so the generic diff leaves it alone. `render` returns None for a
    pair it does not handle.
    """
    src = dict(src)
    dst = dict(dst)
    alters: list[str] = []
    for name in sorted(src.keys() & dst.keys()):
        sql = render(prefix, name, src[name], dst[name])
        if sql is not None:
            alters.append(sql)
            del src[name]
            del dst[name]
    return src, dst, alters


def _validation(prefix: str, name: str, src: Constraint, dst: Constraint) -> str | None:
    """
    A `VALIDATE CONSTRAINT` for a constraint that only transitions NOT VALID -> valid.

    pg_get_constraintdef bakes NOT VALID into the definition, so validating a constraint
    changes its definition string and the generic diff would drop and re-add it -- a full
    re-check under a stronger lock. The reverse (valid -> NOT VALID) has no ALTER form, so it
    is left to fall through to drop-and-re-add.
    """
    if src.definition.endswith(_NOT_VALID_SUFFIX) and src.definition[: -len(_NOT_VALID_SUFFIX)] == dst.definition:
        return f"{prefix} VALIDATE CONSTRAINT {ident(name)};"
    return None


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


def _deferrability_alter(prefix: str, name: str, src: Constraint, dst: Constraint) -> str | None:
    """
    An in-place ALTER CONSTRAINT for a foreign key that differs only in its deferrability.

    The DEFERRABLE / INITIALLY DEFERRED clause rides in the pg_get_constraintdef definition, so
    the generic diff would drop and re-add such a constraint. Foreign keys are the only kind
    Postgres lets change deferrability in place on the supported versions (14-18); every other
    kind (unique, primary key, check, exclusion -- where the recreate rebuilds the backing
    index) never reaches here and falls through to drop-and-re-add.
    """
    if src.definition != dst.definition and _base_definition(src) == _base_definition(dst):
        return f"{prefix} ALTER CONSTRAINT {ident(name)} {_deferrability_clause(dst)};"
    return None


def _enforcement_canonical(definition: str) -> str:
    """The constraint definition with its trailing NOT ENFORCED marker removed."""
    if definition.endswith(_NOT_ENFORCED_SUFFIX):
        return definition[: -len(_NOT_ENFORCED_SUFFIX)]
    return definition


def _enforcement_alter(prefix: str, name: str, src: Constraint, dst: Constraint) -> str | None:
    """
    An in-place `ALTER CONSTRAINT ... [NOT] ENFORCED` for a foreign key whose definitions are
    equal modulo the NOT ENFORCED suffix -- an enforced-state-only change (Postgres 18+).

    Only foreign keys reach here: Postgres rejects altering a check constraint's enforceability
    in place, so a check falls through to the drop + re-add.
    """
    if src.definition != dst.definition and _enforcement_canonical(src.definition) == _enforcement_canonical(
        dst.definition
    ):
        state = "NOT ENFORCED" if dst.definition.endswith(_NOT_ENFORCED_SUFFIX) else "ENFORCED"
        return f"{prefix} ALTER CONSTRAINT {ident(name)} {state};"
    return None


def _diff_constraints(
    *,
    schema_name: str,
    table_name: str,
    src: dict[str, Constraint],
    dst: dict[str, Constraint],
    foreign_keys: bool,
) -> tuple[RenameDiff, list[str], list[str]]:
    """
    Diff one table's constraints (of a single kind) into a RenameDiff plus two lists of in-place
    ALTERs that spare an otherwise-needless drop + re-add:
      * deferrability-only and enforced-state-only changes on foreign keys -> ALTER CONSTRAINT ...
      * NOT VALID -> valid transitions -> VALIDATE CONSTRAINT

    pg_get_constraintdef bakes the deferrability clause, the NOT ENFORCED marker, and NOT VALID
    into the definition string, so the generic key comparison would see any of them as a changed
    definition and drop + re-add it -- rebuilding the backing index (deferrability on
    unique/primary keys) or re-checking every row under a stronger lock (validation). Each matched
    pair is pulled out; the remainder falls through to the ordinary diff. Reverse or unsupported
    transitions (valid -> NOT VALID, and deferrability/enforceability on non-foreign-key kinds)
    have no in-place ALTER form and fall through; `foreign_keys` says whether the maps hold
    foreign keys, so the ALTER CONSTRAINT extraction only runs where it can apply.
    """
    prefix = f"ALTER TABLE {qualified(schema_name, table_name)}"
    src, dst, validations = _extract(prefix, src, dst, _validation)
    alters: list[str] = []
    if foreign_keys:
        src, dst, deferrability_alters = _extract(prefix, src, dst, _deferrability_alter)
        src, dst, enforcement_alters = _extract(prefix, src, dst, _enforcement_alter)
        alters = [*deferrability_alters, *enforcement_alters]
    diff = diff_renamable(
        src,
        dst,
        key=lambda constraint: constraint.definition,
        render_drop=lambda name: f"{prefix} DROP CONSTRAINT {ident(name)};",
        render_rename=lambda old, new: f"{prefix} RENAME CONSTRAINT {ident(old)} TO {ident(new)};",
        render_create=lambda name, constraint: f"{prefix} ADD CONSTRAINT {ident(name)} {constraint.definition};",
    )
    return diff, alters, validations


def _blocks_column_removal(constraint: Constraint, removed: frozenset[str]) -> bool:
    """
    Whether this run's column removals would be refused rather than cascaded because of this
    constraint: it reaches a removed column only through an expression or WHERE predicate in
    its backing index, which records no dependency of the constraint's own. Postgres then sees
    the constraint as a non-auto dependent of the column and rejects the DROP COLUMN, so the
    constraint has to go first.
    """
    return constraint.dependency_columns.isdisjoint(removed) and not constraint.index_dependency_columns.isdisjoint(
        removed
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

        removed = removed_columns(src_table, dst_table)
        all_src_constraints = src_table.constraint_by_name if src_table else {}
        # A constraint Postgres would refuse to cascade is dropped before the column removal
        # it blocks. Both it and the constraints that do cascade away are then out of the
        # ordinary diff below, which re-adds whichever the target still declares.
        blocking = {name for name, con in all_src_constraints.items() if _blocks_column_removal(con, removed)}
        for name in sorted(blocking):
            yield Statement(
                Phase.CONSTRAINT_DROP_EARLY,
                f"ALTER TABLE {qualified(schema_name, table_name)} DROP CONSTRAINT {ident(name)};",
            )
        src_constraints = without_column_removal_cascades(
            {name: con for name, con in all_src_constraints.items() if name not in blocking}, removed
        )
        dst_constraints = dst_table.constraint_by_name
        (drops, renames, adds, recreated, renamed_from), _alters, validations = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_constraints,
            dst=dst_constraints,
            foreign_keys=False,
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
        # No non-foreign-key constraint kind supports an in-place deferrability / enforceability
        # change, so those fall through to the drop + re-add above.
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
        (drops, renames, adds, recreated, renamed_from), alters, validations = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_fks,
            dst=dst_fks,
            foreign_keys=True,
        )
        for sql in drops:
            yield Statement(Phase.FOREIGN_KEY_DROP, sql)
        # Renames, in-place ALTER CONSTRAINTs (deferrability / enforceability), and validations
        # carry no referenced-object dependency (validations only touch the constraint's own rows),
        # so they ride with the adds.
        comments = diff_child_comment_statements(
            schema_name, table_name, src_fks, dst_fks, kind="CONSTRAINT", recreated=recreated, renamed_from=renamed_from
        )
        for sql in (*renames, *alters, *adds, *validations, *comments):
            yield Statement(Phase.FOREIGN_KEY_ADD, sql)
