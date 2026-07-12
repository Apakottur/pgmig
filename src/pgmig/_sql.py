"""
Primitives for rendering safe SQL: identifier quoting and string literal escaping.
"""


def ident(name: str) -> str:
    """
    Quote a single SQL identifier, doubling any embedded double quotes.
    """
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def qualified(*parts: str) -> str:
    """
    Quote and dot-join a dotted identifier (e.g. schema.table.column).
    """
    return ".".join(ident(part) for part in parts)


def literal(text: str) -> str:
    """
    Render a SQL string literal, doubling any embedded single quotes.
    """
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def comment_on(kind: str, path: str, comment: str | None) -> str:
    """
    Render a COMMENT ON statement for any object kind.

    Args:
        kind: the object keyword (e.g. "TABLE", "COLUMN").
        path: the already-quoted object path.
        comment: the comment text, or None to remove the comment. An empty
            string is a real (empty) comment and renders as '', not NULL.
    """
    value = "NULL" if comment is None else literal(comment)
    return f"COMMENT ON {kind} {path} IS {value};"
