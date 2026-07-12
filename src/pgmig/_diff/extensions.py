from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement
from pgmig._models import DbInfo
from pgmig._sql import ident, literal


def generate(*, source: DbInfo, target: DbInfo) -> Iterator[Statement]:
    """
    Generate the migration SQL of extensions.
    """
    for name in sorted(source.extension_by_name.keys() | target.extension_by_name.keys()):
        # Present in target only: create it.
        if name not in source.extension_by_name:
            dst_ext = target.extension_by_name[name]
            yield Statement(
                Phase.EXTENSION,
                f"CREATE EXTENSION {ident(dst_ext.name)} VERSION {literal(dst_ext.version)}"
                f" SCHEMA {ident(dst_ext.schema)};",
            )
        # Present in source only: drop it.
        elif name not in target.extension_by_name:
            src_ext = source.extension_by_name[name]
            yield Statement(Phase.EXTENSION, f"DROP EXTENSION {ident(src_ext.name)};")

        # Present in both: alter version and/or schema if they differ.
        else:
            src_ext = source.extension_by_name[name]
            dst_ext = target.extension_by_name[name]
            if src_ext.version != dst_ext.version:
                yield Statement(
                    Phase.EXTENSION,
                    f"ALTER EXTENSION {ident(dst_ext.name)} UPDATE TO {literal(dst_ext.version)};",
                )
            if src_ext.schema != dst_ext.schema:
                yield Statement(
                    Phase.EXTENSION, f"ALTER EXTENSION {ident(dst_ext.name)} SET SCHEMA {ident(dst_ext.schema)};"
                )
