from enum import StrEnum


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
    def resolved(self) -> "DbDriver":
        match self:
            case DbDriver.AUTO:
                return DbDriver.PSYCOPG
            case _:
                return self
