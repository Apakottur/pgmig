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
            # CASCADE auto-creates any prerequisite extensions (so alphabetical emit order
            # can't break inter-extension dependencies), and IF NOT EXISTS tolerates one
            # already installed that way. The VERSION is deliberately omitted: pinning the
            # source's exact version breaks portability across servers, so the target
            # installs whatever version the applying server offers.
            yield Statement(
                Phase.EXTENSION,
                f"CREATE EXTENSION IF NOT EXISTS {ident(dst_ext.name)} SCHEMA {ident(dst_ext.schema)} CASCADE;",
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
