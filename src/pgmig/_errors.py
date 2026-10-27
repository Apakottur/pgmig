from pgmig._drivers import DbDriver


class PgmigError(Exception):
    """
    A known, user-facing pgmig error (e.g. an invalid connection string).
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PgmigUnsupportedError(PgmigError):
    """
    The database is in a state that pgmig does not yet support.
    """


class PgmigApiError(PgmigError):
    """
    The pgmig API was used incorrectly.
    """


class PgmigInvalidDbDsnError(PgmigError):
    """
    An error occurred while parsing a DB connection string.
    """

    def __init__(self) -> None:
        super().__init__(
            "Invalid connection string. The driver's own message is not shown here because "
            "it quotes the connection string back, password included."
        )


class PgmigDbDriverError(PgmigError):
    """
    An error occurred while connecting to a database via the DB driver.
    """

    def __init__(self, *, label: str, driver: DbDriver, driver_error: Exception) -> None:
        self.label = label
        self.driver = driver
        self.driver_error = driver_error
        super().__init__(f"Could not connect to {label} database.")


class PgmigDbConnectionError(PgmigError):
    """
    At least one of a run's two databases could not be connected to.
    """

    def __init__(self, *, source_error: PgmigDbDriverError | None, target_error: PgmigDbDriverError | None) -> None:
        self.source_error = source_error
        self.target_error = target_error
        super().__init__("Failed to connect to one of the databases")


class PgmigDbIdleTimeoutError(PgmigError):
    """
    The database ended pgmig's introspection transaction for sitting idle past idle_in_transaction_session_timeout.
    """

    def __init__(self, *, label: str) -> None:
        self.label = label
        super().__init__(
            f"The {label} database ended pgmig's introspection transaction because it sat idle longer than the "
            "server's idle_in_transaction_session_timeout. Raise the limit for pgmig's connection, e.g. by adding "
            "options=-c%20idle_in_transaction_session_timeout%3D0 to the connection string."
        )
