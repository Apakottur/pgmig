from pgmig._diff import (
    composite_types,
    constraints,
    default_privileges,
    domains,
    enums,
    extensions,
    functions,
    indexes,
    materialized_views,
    matview_indexes,
    policies,
    range_types,
    schemas,
    sequences,
    tables,
    triggers,
    views,
)
from pgmig._diff._context import ContextData, context_scope
from pgmig._diff._core import Generator, Phase

# Cross-phase ordering is decided by each statement's phase, but WITHIN a single phase
# statements keep this registration order (the collection loop is a stable sort). So this
# order is load-bearing wherever two kinds share a phase and one depends on the other:
#   enums before domains before composite_types before range_types -- a later type may use an
#     earlier one as a field/base/subtype (all Phase.TYPE_CREATE).
# A new object kind is a new module plus one entry here.
_GENERATORS: list[Generator] = [
    schemas.generate,
    extensions.generate,
    enums.generate,
    domains.generate,
    composite_types.generate,
    range_types.generate,
    sequences.generate,
    tables.generate,
    indexes.generate,
    constraints.generate,
    constraints.generate_foreign_keys,
    functions.generate,
    triggers.generate,
    policies.generate,
    views.generate,
    materialized_views.generate,
    matview_indexes.generate,
    default_privileges.generate,
]


def get_diff(data: ContextData) -> str:
    """
    Get the migration SQL for the given diff context.
    """
    # Initialize the dictionary with all phases.
    statements_by_phase: dict[Phase, list[str]] = {phase: [] for phase in Phase}

    # Run within the diff context.
    with context_scope(data):
        # Collect all statements by phase.
        for generate in _GENERATORS:
            for statement in generate():
                statements_by_phase[statement.phase].append(statement.sql)

    # Join all statements in phase declaration order.
    return "\n".join(sql for phase in Phase for sql in statements_by_phase[phase])
