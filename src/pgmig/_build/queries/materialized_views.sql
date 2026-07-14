-- Materialized views (user matviews only; extension-owned ones are excluded).
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    pg_get_viewdef(c.oid) AS view_definition,
    obj_description(c.oid, 'pg_class') AS view_comment
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind = 'm'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- matview in an extension-owned schema (n.oid)
    --   [x] self leg       -- the matview itself is extension-owned (c.oid)
    --   [ ] owning-table leg -- n/a, a matview is not attached to a table
    {{exclude_extension_owned :n.oid }} {{exclude_extension_owned :c.oid }}
ORDER BY
    n.nspname,
    c.relname;
