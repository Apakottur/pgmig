from collections.abc import Sequence

from pgmig._diff import (
    composite_types,
    constraints,
    domains,
    enums,
    extensions,
    functions,
    indexes,
    materialized_views,
    matview_indexes,
    schemas,
    sequences,
    tables,
    triggers,
    views,
)
from pgmig._diff._context import context
from pgmig._diff._core import Generator, Phase
from pgmig._models import DbIntrospectionResult

# Cross-phase ordering is decided by each statement's phase, but WITHIN a single phase
# statements keep this registration order (the collection loop is a stable sort). So this
# order is load-bearing wherever two kinds share a phase and one depends on the other:
#   enums before domains before composite_types -- a domain/composite may use an earlier type
#     (all Phase.TYPE_CREATE);
# matview indexes no longer belong here: they were split into Phase.MATVIEW_INDEX_CREATE so
# their dependency on the matview create (Phase.VIEW_CREATE) is structural, not registration-
# order luck. A new object kind is a new module plus one entry here.
_GENERATORS: list[Generator] = [
    schemas.generate,
    extensions.generate,
    enums.generate,
    domains.generate,
    composite_types.generate,
    sequences.generate,
    tables.generate,
    indexes.generate,
    constraints.generate,
    constraints.generate_foreign_keys,
    functions.generate,
    triggers.generate,
    views.generate,
    materialized_views.generate,
    matview_indexes.generate,
]


def get_diff(
    *,
    source: DbIntrospectionResult,
    target: DbIntrospectionResult,
    index_concurrently: bool,
    ignore_extension_version: Sequence[str],
    ignore_owner: bool,
) -> str:
    """
    Get the migration SQL for the current diff context.
    """
    # Initialize the dictionary with all phases.
    statements_by_phase: dict[Phase, list[str]] = {phase: [] for phase in Phase}

    # Run within the diff context.
    with context.context_scope(
        source=source,
        target=target,
        index_concurrently=index_concurrently,
        ignore_extension_version=ignore_extension_version,
        ignore_owner=ignore_owner,
    ):
        # Collect all statements by phase.
        for generate in _GENERATORS:
            for statement in generate():
                statements_by_phase[statement.phase].append(statement.sql)

    # Join all statements in phase declaration order.
    return "\n".join(sql for phase in Phase for sql in statements_by_phase[phase])
