-- Domain types (user domains only; extension-owned ones are excluded).
SELECT
    n.nspname AS schema_name,
    t.typname AS domain_name,
    format_type(t.typbasetype, t.typtypmod) AS data_type,
    t.typnotnull AS not_null,
    t.typdefault AS default_expr,
    obj_description(t.oid, 'pg_type') AS comment,
    pg_get_userbyid(t.typowner) AS domain_owner,
    -- CHECK constraints as {name: definition}; the domain's NOT NULL is a separate
    -- pg_constraint row (contype 'n') and is handled via typnotnull, so keep only 'c'.
    COALESCE((
        SELECT
            jsonb_object_agg(con.conname, pg_get_constraintdef(con.oid))
        FROM pg_constraint con
        WHERE
            con.contypid = t.oid
            AND con.contype = 'c'), '{}'::jsonb) AS checks
FROM
    pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE
    t.typtype = 'd'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- domain in an extension-owned schema (n.oid)
    --   [x] self leg       -- the domain itself is extension-owned (t.oid)
    --   [ ] owning-table leg -- n/a, domains are not attached to a table
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
    n.nspname,
    t.typname;
