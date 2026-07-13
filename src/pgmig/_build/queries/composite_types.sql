-- Standalone composite types (user types only; extension-owned ones are excluded).
-- Every table/view carries an implicit composite row type (typtype 'c'); only a standalone
-- CREATE TYPE ... AS (...) has its typrelid pointing at a pg_class row with relkind 'c', so
-- that join leg distinguishes real composite types from relation row types.
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    obj_description(t.oid, 'pg_type') AS type_comment,
    jsonb_agg(jsonb_build_object('name', a.attname, 'type', format_type(a.atttypid, a.atttypmod))
    ORDER BY a.attnum) AS fields
FROM
    pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    JOIN pg_class c ON c.oid = t.typrelid
    JOIN pg_attribute a ON a.attrelid = t.typrelid
WHERE
    t.typtype = 'c'
    AND c.relkind = 'c'
    AND a.attnum > 0
    AND NOT a.attisdropped
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- composite type in an extension-owned schema (n.oid)
    --   [x] self leg       -- the composite type itself is extension-owned (t.oid)
    --   [ ] owning-table leg -- n/a, a standalone composite type is not attached to a table
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
