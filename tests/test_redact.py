from pgmig._redact import redact_dsn_secrets


def test_redact_uri_password() -> None:
    text = 'bad thing near "postgresql://user:secretpw@localhost:5432/db"'
    assert redact_dsn_secrets(text) == 'bad thing near "postgresql://user:***@localhost:5432/db"'


def test_redact_uri_password_without_scheme() -> None:
    # The DSN libpq fails to parse is the one missing its scheme, and it echoes only the
    # offending token, not the whole string.
    assert redact_dsn_secrets('missing "=" after "user:secretpw@x"') == 'missing "=" after "user:***@x"'


def test_redact_keyword_password_unquoted() -> None:
    text = "invalid: host=localhost password=secretpw dbname=db"
    assert redact_dsn_secrets(text) == "invalid: host=localhost password=*** dbname=db"


def test_redact_keyword_password_quoted() -> None:
    text = "invalid: host=localhost password='my secretpw' dbname=db"
    assert redact_dsn_secrets(text) == "invalid: host=localhost password=*** dbname=db"


def test_redact_no_password_leaves_text_unchanged() -> None:
    text = 'bad thing near "postgresql://user@localhost:5432/db"'
    assert redact_dsn_secrets(text) == text


def test_redact_empty_uri_password_ignored() -> None:
    # There is no secret here, and masking would invent one.
    text = 'bad thing near "postgresql://user:@localhost:5432/db"'
    assert redact_dsn_secrets(text) == text


def test_redact_empty_keyword_password_ignored() -> None:
    text = "invalid: host=localhost password='' dbname=db"
    assert redact_dsn_secrets(text) == text


def test_redact_leaves_fields_that_repeat_the_password_alone() -> None:
    # Dev DSNs routinely reuse one word as user, password and database prefix. Only text
    # that says a value is a password is masked, so the database name survives intact.
    text = 'connection failed: FATAL:  database "pgmig_dst_main" does not exist'
    assert redact_dsn_secrets(text) == text


def test_redact_leaves_the_multi_address_failure_list_alone() -> None:
    # The per-address breakdown is full of colons but carries no password.
    text = (
        "- host: 'localhost', port: '15432', hostaddr: '::1': connection failed: connection to "
        'server at "::1", port 15432 failed: FATAL:  role "app@corp" does not exist'
    )
    assert redact_dsn_secrets(text) == text
