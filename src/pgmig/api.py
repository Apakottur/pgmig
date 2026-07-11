from dataclasses import dataclass, field

import psycopg
from psycopg import sql


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
    Database schema.
    """

    extensions: dict[str, Extension] = field(default_factory=dict)


def _get_db_schema(dsn: str) -> Schema:
    """
    Get the database schema from the given DSN.
    """
    # Start with an empty schema.
    s = Schema()

    # Construct schema attributes.
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        # Extensions.
        rows = conn.execute(
            "SELECT e.extname, e.extversion, n.nspname "
            "FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace"
        ).fetchall()
        for name, version, schema in rows:
            s.extensions[name] = Extension(name=name, version=version, schema=schema)

    # Return the schema.
    return s


def _get_migration_sql(*, source: Schema, target: Schema) -> str:
    """
    Get the migration SQL between the given source and target schemas.
    """
    statements: list[str] = []

    # Extensions.
    for name in sorted(source.extensions.keys() | target.extensions.keys()):
        if name not in source.extensions:
            # Present in target only: create it.
            dst_ext = target.extensions[name]
            statements.append(
                sql.SQL("CREATE EXTENSION {name} VERSION {version} SCHEMA {schema};")
                .format(
                    name=sql.Identifier(dst_ext.name),
                    version=sql.Literal(dst_ext.version),
                    schema=sql.Identifier(dst_ext.schema),
                )
                .as_string()
            )
        elif name not in target.extensions:
            # Present in source only: drop it.
            src_ext = source.extensions[name]
            statements.append(sql.SQL("DROP EXTENSION {name};").format(name=sql.Identifier(src_ext.name)).as_string())
        else:
            # Present in both: alter version and/or schema if they differ.
            src_ext = source.extensions[name]
            dst_ext = target.extensions[name]
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

    return "\n".join(statements)


def generate(*, source: str, target: str) -> str:
    """
    Generate the migration SQL between the given source and target databases.
    """
    # Get source schema.
    source_schema = _get_db_schema(source)

    # Get target schema.
    target_schema = _get_db_schema(target)

    # Get the migration SQL.
    return _get_migration_sql(source=source_schema, target=target_schema)
