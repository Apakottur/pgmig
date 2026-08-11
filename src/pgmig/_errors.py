from pgmig._drivers import DbDriver


class _PgmigError(Exception):
    """
    A known, user-facing pgmig error (e.g. an invalid connection string).
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PgmigUnsupportedError(_PgmigError):
    """
    The database is in a state that pgmig does not yet support.
    """


class PgmigApiError(_PgmigError):
    """
    The pgmig API was used incorrectly.
    """


class InvalidDsnError(Exception):
    """
    Stands in for a driver error raised while parsing a connection string.

    Those errors quote the string they could not parse -- password and all -- so the
    driver's own words are dropped in favour of these, and the original is left as the
    raised exception's cause for anyone who needs it.
    """

    def __init__(self) -> None:
        super().__init__(
            "Invalid connection string. The driver's own message is not shown here because "
            "it quotes the connection string back, password included."
        )


class DbDriverError(_PgmigError):
    """
    An error occurred while connecting to a database via the DB driver.
    """

    def __init__(self, *, label: str, driver: DbDriver, driver_error: Exception) -> None:
        self.label = label
        self.driver = driver
        self.driver_error = driver_error
        super().__init__(f"Could not connect to {label} database.")


class DbConnectionError(_PgmigError):
    """
    At least one of a run's two databases could not be connected to.
    """

    def __init__(self, *, source_error: DbDriverError | None, target_error: DbDriverError | None) -> None:
        self.source_error = source_error
        self.target_error = target_error
        super().__init__("Failed to connect to one of the databases")
