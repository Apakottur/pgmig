-- Unsupported object kinds. None are modelled yet, so their presence must raise rather
-- than let generate() return "" and falsely claim convergence. Each leg mirrors the
-- filter that drops the kind from a sibling loader query, so nothing slips through both.
--   pg_class relkind:     foreign table 'f'.
--   pg_type typtype:      range 'r'.
--   pg_constraint contype: exclusion 'x'   (dropped by constraints.sql's contype filter).
--   pg_proc prokind:      aggregate 'a', window 'w'   (dropped by functions.sql's prokind filter).
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
    c.relkind = 'f'
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
UNION ALL
-- Exclusion constraints ('x'), dropped by constraints.sql's contype filter. Same
-- conparentid = 0 guard as constraints.sql so a partition-inherited copy is not
-- double-reported alongside the parent declaration.
SELECT
    n.nspname AS schema_name,
    con.conname AS obj_name,
    con.contype AS kind
FROM
    pg_constraint con
    JOIN pg_class c ON c.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    con.contype = 'x'
    AND c.relkind IN ('r', 'p')
    AND con.conparentid = 0
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
-- Aggregate ('a') and window ('w') functions, dropped by functions.sql's prokind filter.
SELECT
    n.nspname AS schema_name,
    p.proname AS obj_name,
    p.prokind AS kind
FROM
    pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE
    p.prokind IN ('a', 'w')
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
            d.objid = p.oid
            AND d.deptype = 'e')
ORDER BY
    schema_name,
    obj_name;
