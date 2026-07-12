-- Extensions (database-level).
SELECT
    e.extname,
    e.extversion,
    n.nspname
FROM
    pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace;
