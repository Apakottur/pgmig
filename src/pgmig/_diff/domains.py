from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs, diff_comment_statements, diff_renamable
from pgmig._models import Domain
from pgmig._sql import ident, qualified


def _create_domain(qualified_name: str, domain: Domain) -> list[str]:
    """
    Render CREATE DOMAIN (base type, DEFAULT and NOT NULL inline) plus one
    ALTER DOMAIN ADD CONSTRAINT per named CHECK.
    """
    parts = [f"CREATE DOMAIN {qualified_name} AS {domain.data_type}"]
    if domain.default is not None:
        parts.append(f"DEFAULT {domain.default}")
    if domain.not_null:
        parts.append("NOT NULL")
    return [
        f"{' '.join(parts)};",
        *(
            f"ALTER DOMAIN {qualified_name} ADD CONSTRAINT {ident(name)} {domain.check_by_name[name]};"
            for name in sorted(domain.check_by_name)
        ),
    ]


def _alter_domain(qualified_name: str, src: Domain, dst: Domain) -> list[str]:
    """
    Sync a domain present on both sides: DEFAULT, NOT NULL and CHECK constraints. A base
    type change is unsupported (ALTER DOMAIN cannot change the type) and raises.
    """
    if src.data_type != dst.data_type:
        raise NotImplementedError(
            f"Domain base type change is not supported: {qualified_name} {src.data_type} -> {dst.data_type}"
        )

    statements: list[str] = []
    if src.default != dst.default:
        if dst.default is None:
            statements.append(f"ALTER DOMAIN {qualified_name} DROP DEFAULT;")
        else:
            statements.append(f"ALTER DOMAIN {qualified_name} SET DEFAULT {dst.default};")
    if src.not_null != dst.not_null:
        statements.append(f"ALTER DOMAIN {qualified_name} {'SET' if dst.not_null else 'DROP'} NOT NULL;")

    # CHECK constraints diff by name-independent definition, so a same-definition rename
    # is a RENAME rather than a drop + add.
    drops, renames, adds, _recreated = diff_renamable(
        src.check_by_name,
        dst.check_by_name,
        key=lambda definition: definition,
        render_drop=lambda name: f"ALTER DOMAIN {qualified_name} DROP CONSTRAINT {ident(name)};",
        render_rename=lambda old, new: f"ALTER DOMAIN {qualified_name} RENAME CONSTRAINT {ident(old)} TO {ident(new)};",
        render_create=lambda name, definition: (
            f"ALTER DOMAIN {qualified_name} ADD CONSTRAINT {ident(name)} {definition};"
        ),
    )
    statements.extend(drops)
    statements.extend(renames)
    statements.extend(adds)
    return statements


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of domain types (create, drop, alter). Creates and alters
    are phased before tables (a column may be of the domain); drops run after.
    """
    for schema_name, src_domains, dst_domains, pairs in ctx_iter_object_pairs(lambda schema: schema.domain_by_name):
        for name, src_domain, dst_domain in pairs:
            qualified_name = qualified(schema_name, name)

            # Present in target only: create it.
            if src_domain is None:
                for sql in _create_domain(qualified_name, dst_domains[name]):
                    yield Statement(Phase.TYPE_CREATE, sql)
            # Present in source only: drop it.
            elif dst_domain is None:
                yield Statement(Phase.TYPE_DROP, f"DROP DOMAIN {qualified_name};")
            # Present in both: alter what differs.
            else:
                for sql in _alter_domain(qualified_name, src_domain, dst_domain):
                    yield Statement(Phase.TYPE_CREATE, sql)

        # Sync comments for target domains, after the domains they annotate exist.
        for sql in diff_comment_statements(schema_name, src_domains, dst_domains, kind="DOMAIN"):
            yield Statement(Phase.TYPE_CREATE, sql)
