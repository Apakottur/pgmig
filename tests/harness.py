from dataclasses import dataclass

import psycopg


@dataclass(frozen=True)
class Db:
    """A handle to one test database."""

    dsn: str

    def run(self, query: str) -> None:
        """Execute a SQL statement against this database."""
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # Test SQL is developer-authored and may be built dynamically;
            # encode to bytes to bypass psycopg's LiteralString query guard.
            conn.execute(query.encode())


@dataclass(frozen=True)
class GenerateSetup:
    """The pair of databases a `generate` test compares: source and target."""

    db_src: Db
    db_dst: Db
