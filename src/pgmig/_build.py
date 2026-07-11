import psycopg

from pgmig._models import Extension, Schema


def build_schema(dsn: str) -> Schema:
    """
    Build the database schema of the given database.
    """
    extension_by_name = {}

    # Construct schema attributes.
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        # Extensions.
        rows = conn.execute(
            "SELECT e.extname, e.extversion, n.nspname "
            "FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace"
        ).fetchall()
        for name, version, schema in rows:
            extension_by_name[name] = Extension(name=name, version=version, schema=schema)

    # Build and return the schema.
    return Schema(
        extension_by_name=extension_by_name,
    )
