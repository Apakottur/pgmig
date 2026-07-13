import pytest

from pgmig._build._engine import build_db_info
from pgmig._errors import PgmigError
from pgmig._redact import redact_dsn_secrets


def test_redact_uri_password() -> None:
    dsn = "postgresql://user:secretpw@localhost:5432/db"
    assert (
        redact_dsn_secrets(f'bad thing near "{dsn}"', dsn) == 'bad thing near "postgresql://user:***@localhost:5432/db"'
    )


def test_redact_keyword_password_unquoted() -> None:
    dsn = "host=localhost password=secretpw dbname=db"
    assert redact_dsn_secrets(f"invalid: {dsn}", dsn) == "invalid: host=localhost password=*** dbname=db"


def test_redact_keyword_password_quoted() -> None:
    dsn = "host=localhost password='my secretpw' dbname=db"
    assert redact_dsn_secrets(f"invalid: {dsn}", dsn) == "invalid: host=localhost password='***' dbname=db"


def test_redact_no_password_leaves_text_unchanged() -> None:
    dsn = "postgresql://user@localhost:5432/db"
    text = f'bad thing near "{dsn}"'
    assert redact_dsn_secrets(text, dsn) == text


def test_redact_password_occurring_twice() -> None:
    dsn = "postgresql://user:secretpw@localhost/db"
    text = "secretpw failed, offending string: secretpw"
    assert redact_dsn_secrets(text, dsn) == "*** failed, offending string: ***"


def test_redact_empty_password_ignored() -> None:
    dsn = "postgresql://user:@localhost:5432/db"
    text = f'bad thing near "{dsn}"'
    assert redact_dsn_secrets(text, dsn) == text


def test_build_db_info_redacts_password_and_labels_side() -> None:
    # A DSN that fails URI parsing falls back to libpq keyword parsing, whose error
    # echoes the full raw string (including the password). The wrapped PgmigError must
    # carry the side label and the redacted form only.
    dsn = "user:secretpw@localhost:5432/db"

    with pytest.raises(PgmigError) as exc_info:
        build_db_info(dsn, label="source")

    message = exc_info.value.message
    assert "Could not connect to source database" in message
    assert "secretpw" not in message
    assert "***" in message
