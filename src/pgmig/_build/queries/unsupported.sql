-- Unsupported object kinds. None are modelled yet, so their presence must raise rather
-- than let generate() return "" and falsely claim convergence.
--   pg_class relkind:  foreign table 'f'.
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
    c.relkind = 'f'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema' {{exclude_extension_owned :n.oid }} {{exclude_extension_owned :c.oid }}
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
    AND n.nspname <> 'information_schema' {{exclude_extension_owned :n.oid }} {{exclude_extension_owned :t.oid }}
ORDER BY
    schema_name,
    obj_name;
