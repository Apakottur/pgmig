import asyncio

from pgmig._introspect._engine import introspect_db
from tests._api.generate_setup import GenerateSetup


async def test_view_dependencies_exclude_system_and_extension_referenced_views(gen_setup: GenerateSetup) -> None:
    """
    view_dependencies records edges among managed views only. A managed view reading a system
    view (pg_stat_activity) or an extension-owned view (pg_stat_statements) must not produce an
    edge on the referenced side: those relations are not in the model, so an edge to them is
    bogus state that would mislead the ordering and recreate logic.
    """
    gen_setup.src.execute("CREATE EXTENSION pg_stat_statements")
    gen_setup.src.execute("CREATE VIEW v_sys AS SELECT pid FROM pg_stat_activity")
    gen_setup.src.execute("CREATE VIEW v_ext AS SELECT userid FROM pg_stat_statements")

    info = await introspect_db(gen_setup.src.dsn)

    # Every referenced view across all recorded edges lives in a managed (non-system) schema.
    referenced = {ref for refs in info.view_dependencies.values() for ref in refs}
    assert all(not ref.schema.startswith("pg_") and ref.schema != "information_schema" for ref in referenced), (
        f"view_dependencies stored an edge to a non-managed view: {referenced}"
    )
    assert all(ref.name != "pg_stat_statements" for ref in referenced), (
        f"view_dependencies stored an edge to an extension-owned view: {referenced}"
    )
