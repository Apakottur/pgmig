import re

# A URI scheme prefix (postgresql://, postgres://, ...), stripped before the userinfo
# lookup so the scheme's own colon is not mistaken for the user:password separator.
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

# The password of a URI-form userinfo at the start of the (scheme-stripped) DSN:
# user:PASSWORD@. Matching without requiring a scheme keeps a malformed DSN missing the
# postgresql:// prefix (the very case whose parse error echoes the raw string) covered.
_URI_PASSWORD = re.compile(r"^[^:/?@\s]*:([^@\s]*)@")

# The password of a keyword/value-form DSN: password=VALUE or password='VALUE'
# (libpq allows spaces around '=' and backslash escapes inside single quotes).
_KEYWORD_PASSWORD = re.compile(r"password\s*=\s*(?:'((?:\\.|[^'\\])*)'|(\S+))")


def redact_dsn_secrets(text: str, dsn: str) -> str:
    """
    Replace every occurrence in `text` of a password found in `dsn` with `***`.

    libpq error messages can echo the raw connection string (e.g. a DSN that fails URI
    parsing falls back to keyword/value parsing, whose error quotes the full string), so
    any error text derived from a connect attempt must be scrubbed before it is surfaced.
    The password is looked up in the raw DSN by form (URI userinfo and password=...
    keyword) and replaced by value wherever it appears, so it is caught no matter which
    fragment of the DSN the message echoes. Text without the password is returned as is.
    """
    candidates = set()
    userinfo_match = _URI_PASSWORD.match(_SCHEME.sub("", dsn))
    if userinfo_match:
        candidates.add(userinfo_match.group(1))
    for match in _KEYWORD_PASSWORD.finditer(dsn):
        candidates.add(match.group(1) if match.group(1) is not None else match.group(2))

    # Longest first, so a candidate that contains another is replaced whole.
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate:
            text = text.replace(candidate, "***")
    return text
