-- Schemas (user namespaces, excluding system and extension-owned ones).
SELECT
    n.nspname AS schema_name,
    obj_description(n.oid, 'pg_namespace') AS schema_comment,
    pg_get_userbyid(n.nspowner) AS schema_owner,
    -- Effective ACL as a set of (grantee, privilege, grantable). A NULL nspacl means the owner
    -- default, not "no grants", so it is expanded via acldefault('n', owner) -- otherwise every
    -- default-ACL schema would diff. See tables.sql for the full rationale.
    (
        SELECT
	    COALESCE(jsonb_agg(jsonb_build_object('grantee', COALESCE(gr.rolname, 'PUBLIC'), 'privilege',
		acl.privilege_type, 'grantable', acl.is_grantable)), '[]'::jsonb)
        FROM
            aclexplode(COALESCE(n.nspacl, acldefault('n', n.nspowner))) AS acl
        LEFT JOIN pg_roles gr ON gr.oid = acl.grantee) AS schema_grants
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
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = n.oid
            AND d.deptype = 'e')
ORDER BY
    n.nspname;
