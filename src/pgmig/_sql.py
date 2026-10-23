"""
Primitives for rendering safe SQL: identifier quoting and string literal escaping.
"""

# Value bounds per integer type a sequence may use (smallint/integer/bigint only). A
# sequence's default MINVALUE/MAXVALUE are derived from these and the increment sign, so an
# explicitly-set bound can be told apart from a default one.
_SEQUENCE_TYPE_BOUNDS: dict[str, tuple[int, int]] = {
    "smallint": (-32768, 32767),
    "integer": (-2147483648, 2147483647),
    "bigint": (-9223372036854775808, 9223372036854775807),
}


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


def sequence_option_clauses(
    *,
    data_type: str,
    start: int,
    increment: int,
    min_value: int,
    max_value: int,
    cache: int,
    cycle: bool,
) -> list[str]:
    """
    The sequence option clauses that differ from their Postgres default, in declaration order.
    Empty when every option is a default, so the caller can render the bare object.

    The defaults depend on the sign of the increment and on the integer type: an ascending
    sequence runs 1..type_max and a descending one runs type_min..-1, and in both cases the
    start defaults to the range's near end. That near end is the *resolved* bound, not the
    type's -- Postgres applies AS/MINVALUE/MAXVALUE before deriving the default start.

    Shared by standalone sequences (CREATE SEQUENCE) and identity columns (the
    GENERATED ... AS IDENTITY option list), which accept the same options.
    """
    type_min, type_max = _SEQUENCE_TYPE_BOUNDS[data_type]
    ascending = increment > 0
    clauses: list[str] = []
    if start != (min_value if ascending else max_value):
        clauses.append(f"START WITH {start}")
    if increment != 1:
        clauses.append(f"INCREMENT BY {increment}")
    if min_value != (1 if ascending else type_min):
        clauses.append(f"MINVALUE {min_value}")
    if max_value != (type_max if ascending else -1):
        clauses.append(f"MAXVALUE {max_value}")
    if cache != 1:
        clauses.append(f"CACHE {cache}")
    if cycle:
        clauses.append("CYCLE")
    return clauses


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
