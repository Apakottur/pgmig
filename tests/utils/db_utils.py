from typing import Any

import psycopg
import tenacity
from psycopg import sql
from typing_extensions import LiteralString

_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:55432"
_ADMIN_DB_NAME = "postgres"
_ADMIN_DSN = f"{_DSN_PREFIX}/{_ADMIN_DB_NAME}"


def _version_key(version: str) -> tuple[int, ...]:
    """
    Sort key for Postgres extension versions (e.g. '1.10' sorts after '1.4').
    """
    return tuple(int(part) for part in version.split("."))


class DbConnection:
    def __init__(self, db_name: str) -> None:
        self.db_name = db_name
        self.dsn = f"{_DSN_PREFIX}/{db_name}"

        # Recreate the database (if not admin DB).
        if db_name != _ADMIN_DB_NAME:
            self._recreate_database()

        # Wait for the database to be ready.
        self._wait_for_conn()

    def _recreate_database(self) -> None:
        with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
            # Disconnect all DB connections.
            conn.execute(
                sql.SQL("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = {0}").format(
                    sql.Literal(self.db_name)
                )
            )

            # Drop the database, if exists.
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {0}").format(sql.Identifier(self.db_name)))

            # Create the database.
            conn.execute(sql.SQL("CREATE DATABASE {0}").format(sql.Identifier(self.db_name)))

    @tenacity.retry(
        wait=tenacity.wait_fixed(0.5),
        stop=tenacity.stop_after_delay(10),
        reraise=True,
    )
    def _wait_for_conn(self) -> None:
        """
        Wait until a DB connection can be established.
        """
        result = self.execute("SELECT 1")
        assert result == [(1,)]

    def execute(self, query: LiteralString, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        """
        Execute a SQL statement against this database.
        """
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # Execute the query.
            result = conn.execute(query, params)

            # Fetch the results (statements like DDL produce none).
            if result.description is None:
                return []
            return result.fetchall()

    def install_extension(self, name: str, *, version: str | None = None, schema: str | None = None) -> None:
        """
        Install an extension, optionally pinning its version and/or schema.
        """
        stmt = sql.SQL("CREATE EXTENSION {name}").format(name=sql.Identifier(name))
        if version is not None:
            stmt += sql.SQL(" VERSION {version}").format(version=sql.Literal(version))
        if schema is not None:
            stmt += sql.SQL(" SCHEMA {schema}").format(schema=sql.Identifier(schema))

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute(stmt)

    def pick_multi_version_extension(self) -> tuple[str, str, str]:
        """
        Find an extension exposing more than one installable version.

        Returns (name, min_version, max_version), choosing the first extension by
        name so the selection is deterministic across runs.
        """
        rows = self.execute("SELECT name, version FROM pg_available_extension_versions ORDER BY name")
        versions_by_name: dict[str, list[str]] = {}
        for name, version in rows:
            versions_by_name.setdefault(name, []).append(version)

        for name in sorted(versions_by_name):
            versions = sorted(versions_by_name[name], key=_version_key)
            if len(versions) > 1:
                return name, versions[0], versions[-1]

        raise AssertionError("no extension with multiple versions available")

    def extension_info(self, name: str) -> tuple[str, str]:
        """
        Return the installed (version, schema) of the given extension.
        """
        result = self.execute(
            "SELECT e.extversion, n.nspname "
            "FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace "
            "WHERE e.extname = %s",
            (name,),
        )
        assert len(result) == 1, f"extension {name!r} not installed"
        version, schema = result[0]
        return version, schema
