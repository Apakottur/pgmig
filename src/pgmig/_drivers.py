from enum import Enum


class DbDriver(str, Enum):
    """
    The database driver used to connect to the databases.
    """

    # Pick a driver among the supported ones.
    AUTO = "auto"

    # https://www.psycopg.org/psycopg3/
    PSYCOPG = "psycopg"


# The drivers AUTO chooses between, most preferred first. psycopg is the only implementation
# today, so the choice is currently a formality; this is where a second driver plugs in.
_AUTO_ORDER = (DbDriver.PSYCOPG,)


def resolve_driver(driver: DbDriver) -> DbDriver:
    """
    Resolve AUTO to the driver that will actually be used. A driver named explicitly is
    returned as it is, so a caller that pins one gets it or gets that driver's own error.
    """
    if driver is DbDriver.AUTO:
        return _AUTO_ORDER[0]
    return driver
