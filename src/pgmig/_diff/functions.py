from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import (
    Phase,
    Statement,
    _diff_comments,
    ctx_iter_object_pairs,
    ctx_iter_schema_pairs,
    owner_statements,
    topological_drop_order,
)
from pgmig._errors import PgmigUnsupportedError
from pgmig._keys import FunctionKey, RelationKey
from pgmig._models import Function, FunctionDependent, Table
from pgmig._sql import comment_on, ident, qualified


def _drop_statement(schema_name: str, function: Function) -> str:
    """
    Render the DROP FUNCTION / DROP PROCEDURE statement for a routine (by signature).
    """
    return f"DROP {function.drop_keyword} {qualified(schema_name, function.name)}({function.identity_arguments});"


def _recreate_message(schema_name: str, function: Function, reason: str) -> str:
    """
    The message refusing a return-type-change recreate the dependents path cannot handle.
    """
    return (
        f"Recreating {qualified(schema_name, function.name)}({function.identity_arguments}) "
        f"(return-type change) is not supported: {reason}."
    )


# Dependent kind -> (Table dict attribute holding it, the model attribute compared to decide
# "unchanged" and rendered into the recreate). Membership also gates the supported kinds.
_DEPENDENT_DICT = {"default": "column_by_name", "constraint": "constraint_by_name", "index": "index_by_name"}
_DEPENDENT_SIGNATURE = {"default": "default", "constraint": "definition", "index": "definition"}


def _target_signature(dependent: FunctionDependent, dst_table: Table | None) -> str | None:
    """
    The target-side value the dependent is compared and re-created against (a column's default
    expression, or a constraint/index definition), or None when the dependent's table or the
    dependent itself is absent in the target (dropped -> refuse, handled by the caller).
    """
    objects = {} if dst_table is None else getattr(dst_table, _DEPENDENT_DICT[dependent.kind])
    obj = objects.get(dependent.name)
    return None if obj is None else getattr(obj, _DEPENDENT_SIGNATURE[dependent.kind])


def _dependent_recreate_statements(
    schema_name: str, function: Function, dependent: FunctionDependent
) -> tuple[Statement, Statement]:
    """
    The (drop, recreate) statement pair for one dependent of a return-type-changed routine.

    The drop rides in the dependent's natural phase (TABLE / CONSTRAINT / INDEX -- all ordered
    before FUNCTION_DROP_LATE); the recreate rides in FUNCTION_DEPENDENT_RECREATE (after
    FUNCTION_CREATE). The dependent must be a supported kind and unchanged between source and
    target -- otherwise refuse, since a changed / dropped dependent is handled by its own
    generator in a phase that would bind to the wrong routine (or, for a routine dependent,
    would need recursion the one-level bound rules out).
    """
    if dependent.kind not in _DEPENDENT_DICT:
        raise PgmigUnsupportedError(_recreate_message(schema_name, function, f"a {dependent.kind} depends on it"))

    # The source always holds the dependent (it was introspected from the source routine).
    src_table = context.source.schema_by_name[dependent.schema].table_by_name[dependent.table]
    dst_table = context.target.schema_by_name[dependent.schema].table_by_name.get(dependent.table)
    table = qualified(dependent.schema, dependent.table)

    if dependent.kind == "default":
        prefix = f"ALTER TABLE {table} ALTER COLUMN {ident(dependent.name)}"
        source_value = src_table.column_by_name[dependent.name].default
        drop = Statement(Phase.TABLE, f"{prefix} DROP DEFAULT;")
        recreate = Statement(Phase.FUNCTION_DEPENDENT_RECREATE, f"{prefix} SET DEFAULT {source_value};")
    elif dependent.kind == "constraint":
        source_value = src_table.constraint_by_name[dependent.name].definition
        drop = Statement(Phase.CONSTRAINT, f"ALTER TABLE {table} DROP CONSTRAINT {ident(dependent.name)};")
        recreate = Statement(
            Phase.FUNCTION_DEPENDENT_RECREATE,
            f"ALTER TABLE {table} ADD CONSTRAINT {ident(dependent.name)} {source_value};",
        )
    else:  # index
        source_value = src_table.index_by_name[dependent.name].definition
        drop = Statement(Phase.INDEX, f"DROP INDEX {qualified(dependent.schema, dependent.name)};")
        recreate = Statement(Phase.FUNCTION_DEPENDENT_RECREATE, f"{source_value};")

    # Unchanged only: the target must carry the same dependent verbatim (else it is dropped or
    # changed by its own generator, and re-creating the source version would not converge).
    if _target_signature(dependent, dst_table) != source_value:
        raise PgmigUnsupportedError(
            _recreate_message(schema_name, function, f"its dependent {dependent.kind} {dependent.name} also changed")
        )
    return drop, recreate


def _recreate_with_dependents(schema_name: str, function: Function) -> Iterator[Statement]:
    """
    Drop and re-create a return-type-changed routine around its dependents: drop each
    dependent (in its own phase), drop the routine late (after those drops), and -- once the
    routine is recreated in FUNCTION_CREATE -- re-add each dependent in FUNCTION_DEPENDENT_RECREATE.

    Bounded to one level: a routine-on-routine dependent (or any unsupported / changed
    dependent) raises PgmigUnsupportedError rather than recursing.
    """
    # Resolve every dependent first so an unsupported one refuses before any statement is
    # emitted. Sorted for deterministic output; the recreate order follows this order within
    # the shared FUNCTION_DEPENDENT_RECREATE phase.
    dependents = sorted(function.dependents, key=lambda dep: (dep.kind, dep.schema, dep.table, dep.name))
    resolved = [_dependent_recreate_statements(schema_name, function, dep) for dep in dependents]

    for drop, _recreate in resolved:
        yield drop
    yield Statement(Phase.FUNCTION_DROP_LATE, _drop_statement(schema_name, function))
    for _drop, recreate in resolved:
        yield recreate


def _check_not_circular(schema_name: str, function: Function, dropped_relations: set[RelationKey]) -> None:
    """
    Refuse a late drop that is circular: the routine hard-depends on a relation that is also
    dropped this run. The relation's DROP is phased before FUNCTION_DROP_LATE and would fail
    (the routine still depends on it), while moving the routine earlier would break the
    dependents that forced it late. Postgres needs a manual CASCADE here.
    """
    circular = sorted(function.depends_on_relations & dropped_relations)
    if circular:
        relation = circular[0]
        raise PgmigUnsupportedError(
            f"Dropping {qualified(schema_name, function.name)}({function.identity_arguments}) is not supported: "
            f"it depends on {qualified(relation.schema, relation.name)}, which is also dropped this run "
            f"(a circular dependency that needs a manual CASCADE)."
        )


def _dropped_relations() -> set[RelationKey]:
    """
    Every table, view, and materialized view present in the source but absent in the target
    -- the relations this migration drops.
    """
    dropped: set[RelationKey] = set()
    for schema_name, src_schema, dst_schema in ctx_iter_schema_pairs():
        if src_schema is None:
            continue
        dst_tables = dst_schema.table_by_name if dst_schema else {}
        dst_views = dst_schema.view_by_name if dst_schema else {}
        dst_matviews = dst_schema.materialized_view_by_name if dst_schema else {}
        dropped.update(RelationKey(schema_name, name) for name in src_schema.table_by_name if name not in dst_tables)
        dropped.update(RelationKey(schema_name, name) for name in src_schema.view_by_name if name not in dst_views)
        dropped.update(
            RelationKey(schema_name, name) for name in src_schema.materialized_view_by_name if name not in dst_matviews
        )
    return dropped


def _topological_drop_order(late: dict[FunctionKey, tuple[str, Function]]) -> list[FunctionKey]:
    """
    Order the late-drop set so a routine is dropped before the routines it depends on.
    Edges are each routine's forward function dependencies; `topological_drop_order` reverses
    the dependency-first sort and drops those outside the late set.
    """
    edges = {key: set(value[1].depends_on_functions) for key, value in late.items()}
    return topological_drop_order(set(late), edges)


def _function_comment_statements(
    schema_name: str, src: dict[str, Function], dst: dict[str, Function], recreated: set[str]
) -> list[str]:
    """
    Emit COMMENT ON FUNCTION / PROCEDURE (by kind) for target routines whose comment
    differs from source.
    """
    return _diff_comments(
        src,
        dst,
        render=lambda _signature, func: comment_on(
            func.drop_keyword,
            f"{qualified(schema_name, func.name)}({func.identity_arguments})",
            func.comment,
        ),
        recreated=recreated,
    )


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of functions and procedures. Creates (including
    CREATE OR REPLACE) are phased after tables so routine bodies can reference them.

    Drops are split by dependency: a routine nothing depends on drops early (FUNCTION_DROP,
    before the tables its body may reference); a routine other objects depend on drops late
    (FUNCTION_DROP_LATE, after its dependents -- column defaults, expression indexes, check
    constraints -- and topologically ordered so a routine precedes the routines it depends
    on).
    """
    dropped_relations = _dropped_relations()
    late_drops: dict[FunctionKey, tuple[str, Function]] = {}

    for schema_name, src_functions, dst_functions, pairs in ctx_iter_object_pairs(
        lambda schema: schema.function_by_signature
    ):
        # Routines dropped and recreated (return-type change): CREATE OR REPLACE keeps the
        # comment, but a drop-and-recreate resets it, so its comment must be re-emitted.
        recreated: set[str] = set()
        for signature, src_func, dst_func in pairs:
            # Present in target only: create it.
            if src_func is None:
                # pg_get_functiondef has no trailing semicolon; add one to terminate the statement.
                yield Statement(Phase.FUNCTION_CREATE, f"{dst_functions[signature].definition};")
            # Present in source only: drop it (early if nothing depends on it, else late).
            elif dst_func is None:
                if src_func.has_dependents:
                    _check_not_circular(schema_name, src_func, dropped_relations)
                    late_drops[FunctionKey(schema=schema_name, signature=signature)] = (schema_name, src_func)
                else:
                    yield Statement(Phase.FUNCTION_DROP, _drop_statement(schema_name, src_func))
            # Present in both: re-create if the definition changed.
            elif src_func.definition != dst_func.definition:
                # CREATE OR REPLACE cannot change the return type, so drop first when it differs.
                if src_func.return_type != dst_func.return_type:
                    if src_func.has_dependents:
                        # Drop the dependents, drop the routine late, re-add the dependents after
                        # the recreate (or refuse for a routine chain / changed dependent).
                        yield from _recreate_with_dependents(schema_name, src_func)
                    else:
                        yield Statement(Phase.FUNCTION_DROP, _drop_statement(schema_name, src_func))
                    recreated.add(signature)
                yield Statement(Phase.FUNCTION_CREATE, f"{dst_func.definition};")

            # Reconcile ownership for a routine present on both sides that was not
            # dropped-and-recreated: CREATE OR REPLACE preserves the owner, while a return-type
            # recreate leaves the new routine runner-owned and reconciles on a later run.
            if src_func is not None and dst_func is not None and signature not in recreated:
                for sql in owner_statements(
                    dst_func.drop_keyword,
                    f"{qualified(schema_name, dst_func.name)}({dst_func.identity_arguments})",
                    src_func.owner,
                    dst_func.owner,
                ):
                    yield Statement(Phase.FUNCTION_CREATE, sql)

        # Sync comments for target routines (COMMENT ON FUNCTION / PROCEDURE by kind), after
        # the routines they annotate have been created above.
        for sql in _function_comment_statements(schema_name, src_functions, dst_functions, recreated):
            yield Statement(Phase.FUNCTION_CREATE, sql)

    # Late drops across all schemas, ordered so a routine is dropped before the routines it
    # depends on. Their dependents (column defaults, indexes, constraints) are already gone.
    for key in _topological_drop_order(late_drops):
        schema_name, function = late_drops[key]
        yield Statement(Phase.FUNCTION_DROP_LATE, _drop_statement(schema_name, function))
