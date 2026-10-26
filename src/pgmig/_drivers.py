from enum import StrEnum
from typing import Literal, assert_never


class DbDriver(StrEnum):
    """
    The database driver used to connect to the databases.
    """

    # Pick a driver among the supported ones.
    AUTO = "auto"

    # https://github.com/psycopg/psycopg
    PSYCOPG = "psycopg"

    @property
    def resolved(self) -> "Literal[DbDriver.PSYCOPG]":
        match self:
            case DbDriver.AUTO | DbDriver.PSYCOPG:
                return DbDriver.PSYCOPG
            case _:
                assert_never(self)
