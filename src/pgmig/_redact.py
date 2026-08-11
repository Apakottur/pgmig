import re

_MASK = "***"

# A URI-form password in the userinfo: [scheme://]user:PASSWORD@. The scheme is optional
# because a DSN missing it is exactly the one libpq fails to parse and echoes back. The
# password cannot hold a literal "/" (a URI must percent-encode it there), and saying so
# keeps a match from starting mid-token and swallowing the "//" of the scheme.
_URI_PASSWORD = re.compile(r"(?P<head>(?:[a-zA-Z][a-zA-Z0-9+.-]*://)?[^:/?@\s]*:)[^@\s/]+@")

# A keyword/value-form password: password=VALUE or password='VALUE' (libpq allows spaces
# around '=' and backslash escapes inside single quotes). An empty value is not a secret,
# so both alternatives require at least one character.
_KEYWORD_PASSWORD = re.compile(r"(?P<head>password\s*=\s*)(?:'(?:\\.|[^'\\])+'|[^\s']\S*)")


def redact_dsn_secrets(text: str) -> str:
    """
    Replace any password exposed in `text` with `***`.

    libpq error messages can echo the connection string a connect attempt was given: a
    DSN that fails URI parsing falls back to keyword/value parsing, and that parser
    quotes the offending token verbatim -- password included. Any error text derived
    from a connect attempt must therefore be scrubbed before it is surfaced.

    Matching is on the syntax that makes a value a password (`user:...@`, `password=...`)
    rather than on the password's value, because that is the form libpq echoes it in. A
    value is only masked where the text itself says it is a password, so a password that
    happens to equal the user name or part of the database name cannot corrupt those
    fields elsewhere in the message. Text exposing no password is returned as is.
    """
    text = _URI_PASSWORD.sub(rf"\g<head>{_MASK}@", text)
    return _KEYWORD_PASSWORD.sub(rf"\g<head>{_MASK}", text)
