from dataclasses import dataclass


@dataclass(frozen=True)
class Extension:
    """
    A Postgres extension.
    """

    name: str
    version: str
    schema: str


@dataclass(frozen=True)
class Column:
    """
    A table column.
    """

    name: str
    type: str


@dataclass(frozen=True)
class Table:
    """
    A Postgres table.
    """

    schema: str
    name: str
    columns: tuple[Column, ...]


@dataclass
class Schema:
    """
    Full database schema.
    """

    extension_by_name: dict[str, Extension]
    table_by_key: dict[tuple[str, str], Table]
