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
