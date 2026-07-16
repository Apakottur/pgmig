class _PgmigError(Exception):
    """
    A known, user-facing pgmig error (e.g. an invalid connection string).

    Carries a clean, already-formatted message; the CLI prints this without a
    traceback. Anything that is not a PgmigError is treated as an internal error.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PgmigUnsupportedError(_PgmigError):
    """
    The database is in a state that pgmig does not yet support.
    """
