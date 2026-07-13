from pgmig._diff import (
    composite_types,
    constraints,
    domains,
    enums,
    extensions,
    functions,
    indexes,
    materialized_views,
    schemas,
    sequences,
    tables,
    triggers,
    views,
)
from pgmig._diff._core import Context, Generator, Phase

# Registration order is cosmetic — final ordering is decided by each statement's phase.
# A new object kind is a new module plus one entry here.
_GENERATORS: tuple[Generator, ...] = (
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
)


def generate_migration_sql(*, ctx: Context) -> str:
    """
    Get the migration SQL between the given source and target databases.
    """
    # Collect statements by phase, then join in phase declaration order.
    statements_by_phase: dict[Phase, list[str]] = {phase: [] for phase in Phase}
    for generate in _GENERATORS:
        for statement in generate(ctx):
            statements_by_phase[statement.phase].append(statement.sql)

    return "\n".join(sql for phase in Phase for sql in statements_by_phase[phase])
