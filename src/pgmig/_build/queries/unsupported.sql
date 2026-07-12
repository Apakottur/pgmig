-- Unsupported relation kinds: views ('v'), materialized views ('m'), partitioned
-- tables ('p'), and foreign tables ('f'). None are modelled yet, so their presence
-- must raise rather than let generate() return "" and falsely claim convergence.
-- Extension-owned relations are excluded (the extension recreates them). Drop a relkind
-- from the filter as its roadmap feature lands.
SELECT
    n.nspname AS schema_name,
    c.relname AS rel_name,
    c.relkind::text AS rel_kind
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind IN ('v', 'm', 'p', 'f')
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
ORDER BY
    n.nspname,
    c.relname;
