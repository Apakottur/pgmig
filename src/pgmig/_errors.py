class _PgmigError(Exception):
    """
    A known, user-facing pgmig error (e.g. an invalid connection string).

    Carries a clean, already-formatted message; the CLI prints this without a
    traceback. Anything that is not a PgmigError is treated as an internal error.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PgmigUnsupportedChangeError(_PgmigError):
    """
    A schema diff that pgmig does not yet support.
    """


class PgmigCorruptedIndexError(_PgmigError):
    """
    The schema contains an invalid index, which makes the diff unreliable.
    """
