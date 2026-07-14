import psycopg
import tenacity

from pgmig._build._engine import build_db_info
from tests.api.generate_setup import GenerateSetup


@tenacity.retry(wait=tenacity.wait_fixed(0.5), stop=tenacity.stop_after_delay(15), reraise=True)
def _wait_for_pgbouncer(dsn: str) -> None:
    """
    Wait until pgbouncer is accepting connections (it starts alongside Postgres).
    """
    psycopg.connect(dsn).close()


def test_introspection_through_pgbouncer(gen_setup: GenerateSetup) -> None:
    """
    pgmig must introspect a database reached through pgbouncer, whose transaction pooling
    rejects server-side startup options (-c ...). This exercises the whole introspection
    end to end through the pooler: if the session were configured via startup options the
    connection would be refused ("unsupported startup parameter in options: ...").
    """
    # Create an object on the source database over a direct connection.
    gen_setup.src.execute("CREATE TABLE widget (id integer)")

    # Introspect the same database THROUGH pgbouncer (wildcard-routed, transaction pooling).
    _wait_for_pgbouncer(gen_setup.src.pgbouncer_dsn)
    info = build_db_info(gen_setup.src.pgbouncer_dsn)

    # The full introspection ran through the pooler and saw the object.
    assert "widget" in info.schema_by_name["public"].table_by_name
