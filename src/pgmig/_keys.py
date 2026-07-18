from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class FunctionKey:
    """
    Full function identifier within a database (schema plus overload signature).
    """

    schema: str
    signature: str  # "name(identity_arguments)"


@dataclass(frozen=True, order=True)
class RelationKey:
    """
    Full identifier of a table, view, or materialized view within a database.
    """

    schema: str
    name: str


@dataclass(frozen=True, order=True)
class CompositeTypeKey:
    """
    Full identifier of a standalone composite type within a database.
    """

    schema: str
    name: str


@dataclass(frozen=True, order=True)
class ColumnKey:
    """
    Full identifier of a table column within a database.
    """

    schema: str
    table: str
    column: str


@dataclass(frozen=True, order=True)
class EnumKey:
    """
    Full identifier of an enum type within a database.
    """

    schema: str
    name: str


@dataclass(frozen=True, order=True)
class DefaultAclKey:
    """
    Identifier of an ALTER DEFAULT PRIVILEGES rule within a database: the FOR ROLE target, the
    schema it is scoped to (None for a global rule), and the object-type keyword it applies to.
    """

    role: str
    schema: str | None
    object_type: str
