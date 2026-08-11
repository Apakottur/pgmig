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


class _DbConnectionError(_PgmigError):
    """
    A single database could not be connected to.

    Internal to a run: the API pairs it with the other database's outcome and raises
    DbConnectionError, so this failure is never reported on its own. The driver's error is
    kept as it is rather than rendered here, so whoever reports it decides how it looks.
    """

    def __init__(self, *, label: str, driver_error: Exception) -> None:
        self.driver_error = driver_error
        super().__init__(f"Could not connect to {label} database.")


class DbConnectionError(_PgmigError):
    """
    At least one of a run's two databases could not be connected to. Holds the driver's
    error for each of them, or None where the connection worked, since one side's failure
    says nothing about the other.
    """

    def __init__(self, *, source_error: BaseException | None, target_error: BaseException | None) -> None:
        self.source_error = source_error
        self.target_error = target_error
        super().__init__("\nAt least one of the databases is unreachable:")

    def __str__(self) -> str:
        source = "REACHABLE" if self.source_error is None else f"UNREACHABLE: {self.source_error}"
        target = "REACHABLE" if self.target_error is None else f"UNREACHABLE: {self.target_error}"
        return f"{self.message}\nsource - {source}\ntarget - {target}"
