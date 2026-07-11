from dataclasses import dataclass


@dataclass(frozen=True)
class Extension:
    """
    A Postgres extension. Registered per-database (unique by name), installed into
    a schema.
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
    A Postgres table. Owned by the schema that holds it.
    """

    name: str
    columns: list[Column]


@dataclass
class Schema:
    """
    A Postgres schema (namespace) and the objects it contains.
    """

    name: str
    table_by_name: dict[str, Table]


@dataclass
class DbInfo:
    """
    Full structure of a database: its database-level objects and its schemas.
    """

    extension_by_name: dict[str, Extension]
    schema_by_name: dict[str, Schema]
