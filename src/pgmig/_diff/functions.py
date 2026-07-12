from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, _diff_comments, _iter_schema_pairs
from pgmig._models import DbInfo, Function
from pgmig._sql import comment_on, qualified


def _drop_function_sql(schema_name: str, function: Function) -> str:
    """
    Render the DROP FUNCTION / DROP PROCEDURE statement for a routine (by signature).

    Refuses a routine that other objects depend on (column default, check constraint,
    expression index, another routine, ...): those dependents must be dropped first,
    but they live in phases after FUNCTION_DROP, so the linear ordering would emit an
    invalid migration. Fail loudly until per-statement dependency ordering lands.
    """
    if function.has_dependents:
        raise NotImplementedError(
            f"Dropping {qualified(schema_name, function.name)}({function.identity_arguments}) is not supported: "
            f"another object (column default, check constraint, expression index, or routine) depends on it, "
            f"and dependency-aware drop ordering is not implemented yet."
        )
    return f"DROP {function.drop_keyword} {qualified(schema_name, function.name)}({function.identity_arguments});"


def _function_comment_statements(schema_name: str, src: dict[str, Function], dst: dict[str, Function]) -> list[str]:
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
    )


def generate(*, source: DbInfo, target: DbInfo) -> Iterator[Statement]:
    """
    Generate the migration SQL of functions and procedures. Creates (including
    CREATE OR REPLACE) are phased after tables so routine bodies can reference them;
    drops run early.
    """
    for schema_name, src_schema, dst_schema in _iter_schema_pairs(source, target):
        src_functions = src_schema.function_by_signature if src_schema else {}
        dst_functions = dst_schema.function_by_signature if dst_schema else {}

        for signature in sorted(src_functions.keys() | dst_functions.keys()):
            src_func = src_functions.get(signature)
            dst_func = dst_functions.get(signature)

            # Present in target only: create it.
            if src_func is None:
                # pg_get_functiondef has no trailing semicolon; add one to terminate the statement.
                yield Statement(Phase.FUNCTION_CREATE, f"{dst_functions[signature].definition};")
            # Present in source only: drop it.
            elif dst_func is None:
                yield Statement(Phase.FUNCTION_DROP, _drop_function_sql(schema_name, src_func))
            # Present in both: re-create if the definition changed.
            elif src_func.definition != dst_func.definition:
                # CREATE OR REPLACE cannot change the return type, so drop first when it differs.
                if src_func.return_type != dst_func.return_type:
                    yield Statement(Phase.FUNCTION_DROP, _drop_function_sql(schema_name, src_func))
                yield Statement(Phase.FUNCTION_CREATE, f"{dst_func.definition};")

        # Sync comments for target routines (COMMENT ON FUNCTION / PROCEDURE by kind), after
        # the routines they annotate have been created above.
        for sql in _function_comment_statements(schema_name, src_functions, dst_functions):
            yield Statement(Phase.FUNCTION_CREATE, sql)
