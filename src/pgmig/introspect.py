from psycopg import Connection
from psycopg.rows import TupleRow

from pgmig.model import Schema


def introspect(conn: Connection[TupleRow]) -> Schema:
    # Placeholder: real pg_catalog queries are added in later specs.
    # Run a trivial query so the connection is genuinely exercised.
    conn.execute("SELECT 1")
    return Schema()
