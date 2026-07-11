from dataclasses import dataclass

import psycopg
from psycopg import Connection
from psycopg.rows import TupleRow


@dataclass(frozen=True)
class Schema:
    """A Postgres database schema. Object collections are added in later specs."""


class Change:
    """A single schema change. Concrete variants are added in later specs."""


def _introspect(conn: Connection[TupleRow]) -> Schema:
    # Placeholder: real pg_catalog queries are added in later specs.
    # Run a trivial query so the connection is genuinely exercised.
    conn.execute("SELECT 1")
    return Schema()


def _diff(source: Schema, target: Schema) -> list[Change]:
    # No object types are compared yet; later specs populate this.
    _ = (source, target)
    return []


def _render(changes: list[Change]) -> str:
    # No Change variants are rendered yet; later specs emit real SQL.
    _ = changes
    return ""


def generate(*, source: str, target: str) -> str:
    with (
        psycopg.connect(source) as source_conn,
        psycopg.connect(target) as target_conn,
    ):
        source_schema = _introspect(source_conn)
        target_schema = _introspect(target_conn)
    changes = _diff(source_schema, target_schema)
    return _render(changes)
