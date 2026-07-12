-- Invalid indexes (pg_index.indisvalid = FALSE), almost always the leftover of a failed
-- CREATE INDEX CONCURRENTLY. They occupy the index name but are unusable, and
-- pg_get_indexdef renders them identically to a valid index, so the diff cannot tell
-- them apart. Their presence must raise rather than let generate() emit a colliding
-- CREATE INDEX or falsely claim convergence.
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    ic.relname AS index_name
FROM
    pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    NOT i.indisvalid
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
ORDER BY
    n.nspname,
    c.relname,
    ic.relname;
