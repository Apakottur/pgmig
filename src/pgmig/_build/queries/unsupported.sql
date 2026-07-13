-- Unsupported object kinds. None are modelled yet, so their presence must raise rather
-- than let generate() return "" and falsely claim convergence.
--   pg_class relkind:  partitioned table 'p', foreign table 'f'.
--   pg_type typtype:   range 'r'.
-- Extension-owned objects are excluded (the extension recreates them). Drop a kind from
-- a filter as its roadmap feature lands.
SELECT
    n.nspname AS schema_name,
    c.relname AS obj_name,
    c.relkind AS kind
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind IN ('p', 'f')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = n.oid
            AND d.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = c.oid
            AND d.deptype = 'e')
UNION ALL
SELECT
    n.nspname AS schema_name,
    t.typname AS obj_name,
    t.typtype AS kind
FROM
    pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE
    t.typtype = 'r'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = n.oid
            AND d.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = t.oid
            AND d.deptype = 'e')
ORDER BY
    schema_name,
    obj_name;
