from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    """
    A table column.
    """

    name: str
    type: str
    not_null: bool
    default: str | None
    comment: str | None


@dataclass(frozen=True)
class Index:
    """
    A standalone Postgres index (CREATE INDEX), owned by a table.
    """

    name: str
    definition: str
    # `definition` with the index's own name stripped out, so two indexes that
    # differ only by name compare equal (drives rename detection).
    canonical: str


@dataclass(frozen=True)
class Constraint:
    """
    A Postgres primary key, unique, check, or foreign key constraint, owned by a table.
    """

    name: str
    # pg_get_constraintdef output, e.g. "PRIMARY KEY (id)"; name-independent
    definition: str
    contype: str  # pg_constraint.contype (p, u, c, f, ...)
    columns: list[str]  # key columns in order (for NOT NULL coordination)

    @property
    def is_primary_key(self) -> bool:
        return self.contype == "p"

    @property
    def is_foreign_key(self) -> bool:
        return self.contype == "f"


@dataclass(frozen=True)
class Table:
    """
    A Postgres table. Owned by the schema that holds it.
    """

    name: str
    columns: list[Column]
    comment: str | None
    index_by_name: dict[str, Index]
    constraint_by_name: dict[str, Constraint]
    foreign_key_by_name: dict[str, Constraint]

    def get_primary_key_columns(self) -> set[str]:
        """
        Columns covered by a primary key constraint.
        """
        return {
            column
            for constraint in self.constraint_by_name.values()
            if constraint.is_primary_key
            for column in constraint.columns
        }


@dataclass(frozen=True)
class Sequence:
    """
    A standalone Postgres sequence (not owned by a serial/identity column).
    """

    name: str
    data_type: str
    start: int
    increment: int
    min_value: int
    max_value: int
    cache: int
    cycle: bool


@dataclass
class Schema:
    """
    A Postgres schema (namespace) and the objects it contains.
    """

    name: str
    table_by_name: dict[str, Table]
    sequence_by_name: dict[str, Sequence]


@dataclass(frozen=True)
class Extension:
    """
    A Postgres extension. Registered per-database (unique by name), installed into a schema.
    """

    name: str
    version: str
    schema: str


@dataclass
class DbInfo:
    """
    Full structure of a database.
    """

    schema_by_name: dict[str, Schema]
    extension_by_name: dict[str, Extension]
