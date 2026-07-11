from psycopg import sql

from pgmig._models import Schema


def _generate_extensions(*, source: Schema, target: Schema) -> list[str]:
    """
    Generate the migration SQL of extensions.
    """
    statements: list[str] = []

    for name in sorted(source.extension_by_name.keys() | target.extension_by_name.keys()):
        # Present in target only: create it.
        if name not in source.extension_by_name:
            dst_ext = target.extension_by_name[name]
            statements.append(
                sql.SQL("CREATE EXTENSION {name} VERSION {version} SCHEMA {schema};")
                .format(
                    name=sql.Identifier(dst_ext.name),
                    version=sql.Literal(dst_ext.version),
                    schema=sql.Identifier(dst_ext.schema),
                )
                .as_string()
            )
        # Present in source only: drop it.
        elif name not in target.extension_by_name:
            src_ext = source.extension_by_name[name]
            statements.append(sql.SQL("DROP EXTENSION {name};").format(name=sql.Identifier(src_ext.name)).as_string())

        # Present in both: alter version and/or schema if they differ.
        else:
            src_ext = source.extension_by_name[name]
            dst_ext = target.extension_by_name[name]
            if src_ext.version != dst_ext.version:
                statements.append(
                    sql.SQL("ALTER EXTENSION {name} UPDATE TO {version};")
                    .format(
                        name=sql.Identifier(dst_ext.name),
                        version=sql.Literal(dst_ext.version),
                    )
                    .as_string()
                )
            if src_ext.schema != dst_ext.schema:
                statements.append(
                    sql.SQL("ALTER EXTENSION {name} SET SCHEMA {schema};")
                    .format(
                        name=sql.Identifier(dst_ext.name),
                        schema=sql.Identifier(dst_ext.schema),
                    )
                    .as_string()
                )
    return statements


def generate_schema_migration_sql(*, source: Schema, target: Schema) -> str:
    """
    Get the migration SQL between the given source and target schemas.
    """
    statements: list[str] = []

    # Extensions.
    extensions_statements = _generate_extensions(source=source, target=target)
    statements.extend(extensions_statements)

    # All statements.
    return "\n".join(statements)
