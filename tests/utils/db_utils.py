from typing import Any

import psycopg
import tenacity
from psycopg import sql
from typing_extensions import LiteralString

_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:55432"
_ADMIN_DB_NAME = "postgres"


class DbConnection:
    def __init__(self, db_name: str, admin_conn: "DbConnection | None" = None) -> None:
        # Database name and DSN.
        self._db_name = db_name
        self.dsn = f"{_DSN_PREFIX}/{db_name}"

        # Admin connection.
        self._admin_conn = admin_conn

        # Recreate the database (if not admin DB).
        if db_name != _ADMIN_DB_NAME:
            self._recreate_database()

        # Open a single connection, reused for every query on this database.
        self._conn = self._connect()

    def _recreate_database(self) -> None:
        """
        Recreate the database.
        """
        assert self._admin_conn is not None

        # Drop the database, if exists. WITH (FORCE) atomically terminates any
        # lingering backends and drops the database, avoiding the race between a
        # separate pg_terminate_backend call and the drop.
        self._admin_conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {db_name} WITH (FORCE)").format(db_name=sql.Identifier(self._db_name))
        )

        # Create the database.
        self._admin_conn.execute(sql.SQL("CREATE DATABASE {db_name}").format(db_name=sql.Identifier(self._db_name)))

    @tenacity.retry(
        wait=tenacity.wait_fixed(0.5),
        stop=tenacity.stop_after_delay(10),
        reraise=True,
    )
    def _connect(self) -> psycopg.Connection:
        """
        Open a connection, retrying until the database is ready to accept them.
        """
        return psycopg.connect(self.dsn, autocommit=True)

    def close(self) -> None:
        """
        Close the connection.
        """
        self._conn.close()

    def execute(self, query: LiteralString | sql.Composed) -> list[tuple[Any, ...]]:
        """
        Execute a SQL statement against this database on the reused connection.
        """
        result = self._conn.execute(query)

        # Fetch query results.
        if result.description is None:
            return []
        else:
            return result.fetchall()

    def execute_all(self, queries: list[LiteralString | sql.Composed]) -> None:
        """
        Execute a list of SQL statements against this database on the reused connection.
        """
        for query in queries:
            self.execute(query)
