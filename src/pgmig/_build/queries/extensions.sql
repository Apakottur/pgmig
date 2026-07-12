-- Extensions (database-level).
SELECT
    e.extname AS name,
    e.extversion AS version,
    n.nspname AS extension_schema
FROM
    pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace;
