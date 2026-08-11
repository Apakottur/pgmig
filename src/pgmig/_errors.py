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


class DbDriverError(_PgmigError):
    """
    An error occurred while connecting to a database via the DB driver.
    """

    def __init__(self, *, label: str, driver_error: Exception) -> None:
        self.driver_error = driver_error
        super().__init__(f"Could not connect to {label} database.")


class DbConnectionError(_PgmigError):
    """
    At least one of a run's two databases could not be connected to.
    """

    def __init__(self, *, source_error: BaseException | None, target_error: BaseException | None) -> None:
        self.source_error = source_error
        self.target_error = target_error
        super().__init__("Failed to connect to one of the databases")
