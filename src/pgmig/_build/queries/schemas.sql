-- Schemas (user namespaces, excluding system and extension-owned ones).
SELECT
    n.nspname AS schema_name,
    obj_description(n.oid, 'pg_namespace') AS schema_comment
FROM
    pg_namespace n
WHERE
    n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] self leg       -- the schema itself is extension-owned (n.oid)
    --   [-] namespace leg  -- n/a; a schema is a namespace, not an object inside one
    --   [-] owning-table leg -- n/a; schemas are not attached to a table
    {{exclude_extension_owned :n.oid }}
ORDER BY
    n.nspname;
