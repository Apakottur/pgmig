from pgmig.model import Schema


class Change:
    """A single schema change. Concrete variants are added in later specs."""


def diff(source: Schema, target: Schema) -> list[Change]:
    # No object types are compared yet; later specs populate this.
    _ = (source, target)
    return []
