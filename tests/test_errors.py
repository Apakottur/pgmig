from pgmig._errors import DbConnectionError


def test_connection_error_reports_both_databases() -> None:
    error = DbConnectionError(source_error=None, target_error=OSError("connection refused"))

    # The leading blank line sets the report apart from whatever the terminal printed before it.
    assert error.message == "\nAt least one of the databases is unreachable:"
    assert str(error) == (
        "\nAt least one of the databases is unreachable:\nsource - REACHABLE\ntarget - UNREACHABLE: connection refused"
    )
