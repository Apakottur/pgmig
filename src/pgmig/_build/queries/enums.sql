-- Enum types (user enums only; extension-owned ones are excluded).
SELECT
    n.nspname AS schema_name,
    t.typname AS enum_name,
    array_agg(e.enumlabel ORDER BY e.enumsortorder) AS enum_values,
    obj_description(t.oid, 'pg_type') AS enum_comment
FROM
    pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    JOIN pg_enum e ON e.enumtypid = t.oid
WHERE
    t.typtype = 'e'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- enum in an extension-owned schema (n.oid)
    --   [x] self leg       -- the enum itself is extension-owned (t.oid)
    --   [ ] owning-table leg -- n/a, enums are not attached to a table
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
GROUP BY
    n.nspname,
    t.oid,
    t.typname
ORDER BY
    n.nspname,
    t.typname;
