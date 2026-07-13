"""
Primitives for rendering safe SQL: identifier quoting and string literal escaping.

The schema-aware helpers (`schema_qualified` and the two strip helpers) honor the
omit-schema policy of the current diff generation, read from the diff context
(`context.omit_schema`): outside a diff, or when no schema is omitted, every path
stays fully qualified.
"""

from pgmig._diff._context import context


def ident(name: str) -> str:
    """
    Quote a single SQL identifier, doubling any embedded double quotes.
    """
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def qualified(*parts: str) -> str:
    """
    Quote and dot-join a dotted identifier (e.g. schema.table.column).

    Always fully qualified, regardless of the omit-schema policy; emit sites that honor
    the policy use `schema_qualified` instead.
    """
    return ".".join(ident(part) for part in parts)


def schema_qualified(schema: str, *rest: str) -> str:
    """
    Quote a schema-qualified object path, dropping the schema segment when it equals
    the active omitted schema (see `context.omit_schema`).

    Used for object paths pgmig builds itself (e.g. schema.table, schema.table.column).
    Server-generated definition strings do not pass through here; their qualifier is
    instead suppressed by introspecting with the schema on the search_path (see
    `_build/_engine.py`), plus the two textual helpers below for the spots deparse
    always qualifies.
    """
    if schema == context.omit_schema:
        return qualified(*rest)
    return qualified(schema, *rest)


def strip_on_clause_qualifier(definition: str, schema: str, table: str) -> str:
    """
    Drop the active omitted schema's qualifier from the ` ON schema.table ` clause of a
    server-generated CREATE INDEX / CREATE TRIGGER definition.

    pg_get_indexdef and pg_get_triggerdef always qualify the ON-clause table, even when
    the schema is on the search_path, so this one fixed grammar spot is edited
    textually. The match is anchored to the exact ` ON <schema>.<table> ` text
    (deparse output is single-line, so a trailing space always follows: ` USING ... ` /
    ` FOR EACH ROW ... `), trying each identifier in its unquoted and quoted deparse
    form; when no form matches the definition is returned unchanged (still valid SQL,
    just qualified) rather than risking a wrong edit.
    """
    omit_schema = context.omit_schema
    if omit_schema is None or schema != omit_schema:
        return definition
    for schema_form in (schema, ident(schema)):
        for table_form in (table, ident(table)):
            marker = f" ON {schema_form}.{table_form} "
            if marker in definition:
                return definition.replace(marker, f" ON {table_form} ", 1)
    return definition


def strip_routine_name_qualifier(definition: str, schema: str, name: str) -> str:
    """
    Drop the active omitted schema's qualifier from the routine's own name in a
    pg_get_functiondef header.

    pg_get_functiondef always qualifies the routine's own name (`CREATE OR REPLACE
    FUNCTION schema.name(` or `... PROCEDURE schema.name(`), even when the schema is on
    the search_path, so the header is edited textually. Anchored to the exact prefix,
    trying each identifier in its unquoted and quoted deparse form; when no form
    matches the definition is returned unchanged rather than risking a wrong edit.
    """
    omit_schema = context.omit_schema
    if omit_schema is None or schema != omit_schema:
        return definition
    for keyword in ("FUNCTION", "PROCEDURE"):
        header = f"CREATE OR REPLACE {keyword} "
        if not definition.startswith(header):
            continue
        for schema_form in (schema, ident(schema)):
            for name_form in (name, ident(name)):
                qualified_header = f"{header}{schema_form}.{name_form}("
                if definition.startswith(qualified_header):
                    return definition.replace(qualified_header, f"{header}{name_form}(", 1)
    return definition


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
