from dataclasses import dataclass


@dataclass(frozen=True)
class Schema:
    """A Postgres database schema. Object collections are added in later specs."""
