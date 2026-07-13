from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, _diff_comments, ctx_iter_object_pairs, ctx_iter_schema_pairs
from pgmig._errors import UnsupportedChangeError
from pgmig._models import Function, FunctionKey, RelationKey
from pgmig._sql import comment_on, qualified


def _drop_statement(schema_name: str, function: Function) -> str:
    """
    Render the DROP FUNCTION / DROP PROCEDURE statement for a routine (by signature).
    """
    return f"DROP {function.drop_keyword} {qualified(schema_name, function.name)}({function.identity_arguments});"


def _recreate_drop_sql(schema_name: str, function: Function) -> str:
    """
    DROP for the recreate path (return-type change): CREATE OR REPLACE cannot change the
    return type, so the routine must be dropped and recreated. A routine that other objects
    depend on cannot be dropped while those dependents still reference it (they remain in the
    target), so refuse -- recreating a depended-upon routine would need dropping and
    restoring the dependents too, which is not implemented.
    """
    if function.has_dependents:
        raise UnsupportedChangeError(
            f"Recreating {qualified(schema_name, function.name)}({function.identity_arguments}) "
            f"(return-type change) is not supported: another object depends on it."
        )
    return _drop_statement(schema_name, function)


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
        raise UnsupportedChangeError(
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
    Order the late-drop set so a routine is dropped before the routines it depends on
    (Kahn's algorithm, deterministic by key). Edges are restricted to the late set; hard
    function->function dependencies (SQL-body routines) cannot be cyclic, so this always
    consumes every node.
    """
    keys = set(late)
    # out_edges[F] = routines F depends on that are also dropped late (F must precede them).
    out_edges = {key: {dep for dep in late[key][1].depends_on_functions if dep in keys} for key in keys}
    # in_degree[G] = how many late routines depend on G (each must be dropped before G).
    in_degree = dict.fromkeys(keys, 0)
    for deps in out_edges.values():
        for dep in deps:
            in_degree[dep] += 1

    ready = sorted(key for key in keys if in_degree[key] == 0)
    order: list[FunctionKey] = []
    while ready:
        key = ready.pop(0)
        order.append(key)
        for dep in out_edges[key]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                ready.append(dep)
        ready.sort()
    return order


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
                    yield Statement(Phase.FUNCTION_DROP, _recreate_drop_sql(schema_name, src_func))
                    recreated.add(signature)
                yield Statement(Phase.FUNCTION_CREATE, f"{dst_func.definition};")

        # Sync comments for target routines (COMMENT ON FUNCTION / PROCEDURE by kind), after
        # the routines they annotate have been created above.
        for sql in _function_comment_statements(schema_name, src_functions, dst_functions, recreated):
            yield Statement(Phase.FUNCTION_CREATE, sql)

    # Late drops across all schemas, ordered so a routine is dropped before the routines it
    # depends on. Their dependents (column defaults, indexes, constraints) are already gone.
    for key in _topological_drop_order(late_drops):
        schema_name, function = late_drops[key]
        yield Statement(Phase.FUNCTION_DROP_LATE, _drop_statement(schema_name, function))
