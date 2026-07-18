from dataclasses import dataclass

from pgmig._errors import PgmigUnsupportedError
from pgmig._keys import ColumnKey, CompositeTypeKey, FunctionKey, RelationKey


@dataclass(frozen=True)
class Column:
    """
    A table column.
    """

    name: str
    type: str
    collation: str | None  # explicit collation name when it overrides the type default, else None
    not_null: bool
    default: str | None
    comment: str | None
    identity: str  # pg_attribute.attidentity ('' for a non-identity column)
    serial_sequence: str | None  # sequence owned via a nextval() default, else None
    generated: str  # pg_attribute.attgenerated ('' none, 's' stored, 'v' virtual)
    generation_expression: str | None  # generation expression, kept separate from `default`
    # Backing-sequence options of an identity column (pg_sequence); all None otherwise.
    identity_start: int | None
    identity_increment: int | None
    identity_min: int | None
    identity_max: int | None
    identity_cache: int | None
    identity_cycle: bool | None

    @property
    def serial_type(self) -> str | None:
        """
        The serial pseudo-type to emit ("serial"/"bigserial"/"smallserial"), or None.

        A serial column owns a sequence via its nextval() default and is not an
        identity column; its integer type maps to the matching pseudo-type.

        The nextval() default is load-bearing, not incidental: pg_get_serial_sequence
        resolves `serial_sequence` from the OWNED BY dependency alone, so a column tied to
        a manually created sequence via `ALTER SEQUENCE ... OWNED BY` (with no nextval
        default) also has `serial_sequence` set -- yet it is not serial. Requiring the
        nextval default excludes that manual-ownership case.
        """
        if self.serial_sequence is None or self.identity != "":
            return None
        if self.default is None or not self.default.startswith("nextval("):
            return None
        match self.type:
            case "smallint":
                return "smallserial"
            case "integer":
                return "serial"
            case "bigint":
                return "bigserial"
            case _:
                raise PgmigUnsupportedError(f"Unknown integer type: {self.type}")

    @property
    def identity_kind(self) -> str | None:
        """
        The identity generation kind ("ALWAYS" / "BY DEFAULT") for an identity column,
        or None for a non-identity column.

        Decodes pg_attribute.attidentity: 'a' -> ALWAYS, 'd' -> BY DEFAULT, '' -> None.
        """
        match self.identity:
            case "":
                return None
            case "a":
                return "ALWAYS"
            case "d":
                return "BY DEFAULT"
            case _:
                raise PgmigUnsupportedError(f"Unknown identity kind: {self.identity!r}")

    @property
    def identity_clause(self) -> str | None:
        """
        The GENERATED ... AS IDENTITY clause for an identity column, or None. The backing
        sequence's options are rendered separately at emit time (see the tables diff).
        """
        kind = self.identity_kind
        return None if kind is None else f"GENERATED {kind} AS IDENTITY"


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
    # pg_trigger.tgenabled: the enable state, which pg_get_triggerdef does not carry.
    # O=origin/default, D=disabled, R=enable replica, A=enable always.
    enabled: str
    comment: str | None


@dataclass(frozen=True)
class Constraint:
    """
    A Postgres primary key, unique, check, or foreign key constraint, owned by a table.
    """

    name: str
    # pg_get_constraintdef output, e.g. "PRIMARY KEY (id)"; name-independent. Carries the
    # trailing DEFERRABLE / INITIALLY DEFERRED clause, so the deferrable/deferred booleans
    # below are what the diff compares against once that clause is set aside.
    definition: str
    contype: str  # pg_constraint.contype (p, u, c, f, ...)
    columns: list[str]  # key columns in order (for NOT NULL coordination)
    comment: str | None
    deferrable: bool  # condeferrable: DEFERRABLE
    deferred: bool  # condeferred: DEFERRABLE INITIALLY DEFERRED (implies deferrable)

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

    # Core
    name: str
    columns: list[Column]
    comment: str | None
    owner: str
    unlogged: bool  # UNLOGGED table (relpersistence 'u'); a partitioned parent is always logged
    # Replica identity: pg_class.relreplident ('d' default, 'n' nothing, 'f' full, 'i' using
    # index). replica_identity_index holds the index name when 'i', else None.
    replica_identity: str
    replica_identity_index: str | None

    # Declarative partitioning metadata.
    partition_strategy: str | None
    partition_key: str | None
    partition_bound: str | None
    partition_parent: RelationKey | None

    # Relations.
    index_by_name: dict[str, Index]
    constraint_by_name: dict[str, Constraint]
    foreign_key_by_name: dict[str, Constraint]
    trigger_by_name: dict[str, Trigger]

    @property
    def is_partitioned(self) -> bool:
        """Whether this table is a partitioned parent (declared PARTITION BY ...)."""
        return self.partition_strategy is not None

    @property
    def is_partition(self) -> bool:
        """Whether this table is a partition of some parent."""
        return self.partition_parent is not None

    @property
    def column_by_name(self) -> dict[str, Column]:
        """
        The table's columns indexed by name.

        A plain (recomputed) property rather than a cached one: `columns` is appended to
        row by row during introspection, so a value cached before loading finished would go
        stale. Recomputing on each access keeps it correct at the cost of rebuilding the dict.
        """
        return {column.name: column for column in self.columns}

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
    A standalone Postgres sequence (not the backing sequence of a serial/identity column).

    A sequence may still carry a manual OWNED BY: `owned_by` is the ColumnKey it is tied to,
    or None when it is truly standalone. Unlike a serial/identity backing sequence -- whose
    lifecycle the table layer owns and which is excluded from introspection -- a manually
    owned sequence is a first-class object whose ownership is diffed here.
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
    owned_by: ColumnKey | None
    unlogged: bool  # UNLOGGED sequence (relpersistence 'u'); PG15+ only


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
    # Whether a non-trigger object (column default, check constraint, expression index,
    # another routine, ...) depends on this routine. Drives drop phasing: a routine with
    # dependents is dropped late (after those dependents), one without stays early.
    has_dependents: bool
    # Forward hard dependencies of this routine (pg_depend deptype 'n'):
    #   depends_on_functions -- routines this one depends on; when both are dropped, this
    #     one drops first (topologically ordered in the late phase).
    #   depends_on_relations -- tables/views/matviews the body reads; a late drop is refused
    #     as circular if one of these is also dropped this run.
    depends_on_functions: frozenset[FunctionKey]
    depends_on_relations: frozenset[RelationKey]

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
    # pg_class.reloptions, sorted for order-independent comparison: security_invoker,
    # security_barrier, and check_option (WITH CHECK OPTION) all live here as "key=value"
    # strings. Emitted verbatim in a CREATE VIEW ... WITH (...) clause; empty when the view
    # has none.
    options: tuple[str, ...]
    # INSTEAD OF triggers owned by this view (the only trigger kind a view can carry). Mirrors
    # Table.trigger_by_name so the trigger diff walks views the same way it walks tables.
    trigger_by_name: dict[str, Trigger]


@dataclass(frozen=True)
class MaterializedView:
    """
    A Postgres materialized view, owned by a schema.
    """

    name: str
    definition: str  # pg_get_viewdef output: the SELECT the matview wraps (no trailing semicolon)
    comment: str | None
    index_by_name: dict[str, Index]


@dataclass(frozen=True)
class CompositeField:
    """
    One attribute of a composite type.
    """

    name: str
    type: str  # format_type(atttypid, atttypmod)


@dataclass(frozen=True)
class CompositeType:
    """
    A Postgres standalone composite type (CREATE TYPE ... AS (...)), owned by a schema.
    """

    name: str
    fields: list[CompositeField]  # attributes in attribute (attnum) order
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


@dataclass(frozen=True)
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
    materialized_view_by_name: dict[str, MaterializedView]
    domain_by_name: dict[str, Domain]
    composite_type_by_name: dict[str, CompositeType]


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
class DbIntrospectionResult:
    """
    Full result of a database introspection.
    """

    schema_by_name: dict[str, Schema]
    extension_by_name: dict[str, Extension]

    # Mapping from a view to the set of views it depends on.
    view_dependencies: dict[RelationKey, set[RelationKey]]

    # Mapping from a materialized view to the set of views/matviews it reads from.
    matview_dependencies: dict[RelationKey, set[RelationKey]]

    # Mapping from a view to the set of table columns it reads.
    view_column_dependencies: dict[RelationKey, set[ColumnKey]]

    # Mapping from a composite type to the set of composite types it depends on.
    composite_type_dependencies: dict[CompositeTypeKey, set[CompositeTypeKey]]
