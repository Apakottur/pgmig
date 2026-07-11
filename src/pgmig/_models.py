from dataclasses import dataclass


@dataclass(frozen=True)
class Extension:
    """
    A Postgres extension.
    """

    name: str
    version: str
    schema: str


@dataclass
class Schema:
    """
    Full database schema.
    """

    extension_by_name: dict[str, Extension]
