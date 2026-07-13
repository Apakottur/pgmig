from dataclasses import dataclass
from typing import NewType

# View identifier - schema name and view name.
ViewKey = NewType("ViewKey", tuple[str, str])


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
    identity: str  # pg_attribute.attidentity ('' for a non-identity column)
    serial_sequence: str | None  # sequence owned via a nextval() default, else None

    @property
    def serial_type(self) -> str | None:
        """
        The serial pseudo-type to emit ("serial"/"bigserial"/"smallserial"), or None.

        A serial column owns a sequence via its nextval() default and is not an
        identity column; its integer type maps to the matching pseudo-type.
        """
        if self.serial_sequence is None or self.identity != "":
            return None
        match self.type:
            case "smallint":
                return "smallserial"
            case "integer":
                return "serial"
            case "bigint":
                return "bigserial"
            case _:
                raise NotImplementedError(f"Unknown integer type: {self.type}")


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
    comment: str | None


@dataclass(frozen=True)
class Trigger:
    """
    A Postgres trigger, owned by a table.
    """

    name: str
    definition: str  # pg_get_triggerdef output: a full CREATE TRIGGER ...
    # `definition` with the trigger's own name stripped out, for rename detection.
    canonical: str
    comment: str | None


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
    comment: str | None

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
    trigger_by_name: dict[str, Trigger]

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
    comment: str | None


@dataclass(frozen=True)
class Function:
    """
    A Postgres function or procedure. Identified by name and argument types (overloadable).
    """

    name: str
    identity_arguments: str  # pg_get_function_identity_arguments, e.g. "a integer" (the DROP signature)
    definition: str  # pg_get_functiondef output: a full CREATE OR REPLACE ...
    return_type: str  # format_type(prorettype); "void" for a procedure
    kind: str  # pg_proc.prokind: 'f' (function) or 'p' (procedure)
    comment: str | None
    # Whether a non-trigger object (column default, check constraint, expression
    # index, another routine, ...) depends on this routine. Such a dependent must be
    # dropped before the routine, which the linear phase ordering can't guarantee, so
    # dropping a routine with dependents is refused rather than mis-ordered.
    has_dependents: bool

    @property
    def drop_keyword(self) -> str:
        """
        The DROP object keyword for this routine's kind.
        """
        return "PROCEDURE" if self.kind == "p" else "FUNCTION"


@dataclass(frozen=True)
class EnumType:
    """
    A Postgres enum type, owned by a schema.
    """

    name: str
    values: list[str]  # labels in enum sort order
    comment: str | None


@dataclass(frozen=True)
class View:
    """
    A Postgres view, owned by a schema.
    """

    name: str
    definition: str  # pg_get_viewdef output: the SELECT the view wraps (no trailing semicolon)
    comment: str | None


@dataclass(frozen=True)
class Domain:
    """
    A Postgres domain type, owned by a schema.
    """

    name: str
    data_type: str  # base type, format_type(typbasetype, typtypmod)
    default: str | None  # default expression text (pg_type.typdefault), None if absent
    not_null: bool
    check_by_name: dict[str, str]  # CHECK constraint name -> pg_get_constraintdef ("CHECK (...)")
    comment: str | None


@dataclass
class Schema:
    """
    A Postgres schema (namespace) and the objects it contains.
    """

    name: str
    comment: str | None
    table_by_name: dict[str, Table]
    sequence_by_name: dict[str, Sequence]
    function_by_signature: dict[str, Function]
    enum_by_name: dict[str, EnumType]
    view_by_name: dict[str, View]
    domain_by_name: dict[str, Domain]


@dataclass(frozen=True)
class Extension:
    """
    A Postgres extension. Registered per-database (unique by name), installed into a schema.
    """

    name: str
    version: str
    schema: str
    comment: str | None


@dataclass
class DbInfo:
    """
    Full structure of a database.
    """

    schema_by_name: dict[str, Schema]
    extension_by_name: dict[str, Extension]

    # Mapping from a view to the set of views it depends on.
    view_dependencies: dict[ViewKey, set[ViewKey]]
