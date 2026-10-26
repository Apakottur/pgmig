from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Self, assert_never


class DbDriver(StrEnum):
    """
    The database driver used to connect to the databases.
    """

    # Pick a driver among the supported ones.
    AUTO = "auto"

    # https://github.com/psycopg/psycopg
    PSYCOPG = "psycopg"

    # https://github.com/MagicStack/asyncpg
    ASYNCPG = "asyncpg"

    @property
    def resolved(self) -> "Literal[DbDriver.PSYCOPG, DbDriver.ASYNCPG]":
        match self:
            case DbDriver.AUTO | DbDriver.PSYCOPG:
                return DbDriver.PSYCOPG
            case DbDriver.ASYNCPG:
                return DbDriver.ASYNCPG
            case _:
                assert_never(self)


@dataclass(frozen=True)
class DbConnInfo:
    """
    Information about a single database.
    """

    # The database DSN.
    dsn: str

    # Friendly label, used in error/log messages.
    label: str

    # The driver to connect with.
    driver: DbDriver = DbDriver.AUTO


class DriverConnection(ABC):
    """
    A connection through a single database driver.
    Each driver implements this interface in its own module, and _db.py talks to the driver only through it.
    """

    @classmethod
    @abstractmethod
    def connect(cls, db_conn_info: DbConnInfo) -> AbstractAsyncContextManager[Self]:
        """
        Connection context.
        """

    @abstractmethod
    async def execute(self, statement: str) -> list[tuple[Any, ...]]:
        """
        Execute a statement and return the statement results, if any.
        """

    @abstractmethod
    async def introspect(self, queries: Sequence[str], snapshot_setup: Sequence[str]) -> list[list[dict[str, Any]]]:
        """
        Run the given introspection queries, returning the rows of each one.
        On the first call, first run the snapshot setup statements, which open the snapshot transaction.
        """
