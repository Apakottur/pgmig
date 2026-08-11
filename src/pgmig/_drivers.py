from enum import StrEnum
from typing import Self


class DbDriver(StrEnum):
    """
    The database driver used to connect to the databases.
    """

    # Pick a driver among the supported ones.
    AUTO = "auto"

    # https://github.com/psycopg/psycopg
    PSYCOPG = "psycopg"

    @property
    def resolved(self) -> Self:
        match self:
            case DbDriver.AUTO:
                return DbDriver.PSYCOPG
            case _:
                return self
