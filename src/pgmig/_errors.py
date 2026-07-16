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
