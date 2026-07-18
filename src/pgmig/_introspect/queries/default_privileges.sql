-- ALTER DEFAULT PRIVILEGES rules (pg_default_acl). A row exists only where the defaults were
-- altered; its absence means the built-in defaults apply. So each row is surfaced with both its
-- effective ACL (defaclacl) and the built-in baseline (acldefault of the same object type for the
-- same role) -- the diff compares effective-vs-effective, expanding an absent rule to its baseline.
--
-- defaclobjtype uses its own single-char codes, DISTINCT from acldefault's: 'r' TABLES, 'S'
-- SEQUENCES, 'f' FUNCTIONS, 'T' TYPES, 'n' SCHEMAS (PG15+). acldefault wants the lower-case
-- relation-kind code, so the two are mapped separately below.
SELECT
    pg_get_userbyid(d.defaclrole) AS role,
    -- defaclnamespace 0 is a global (no IN SCHEMA) rule -> NULL schema.
    ns.nspname AS schema_name,
    d.defaclobjtype AS object_type,
    -- Effective ACL: one (grantee, privilege, grantable) row per aclexplode entry. grantee oid 0
    -- is PUBLIC (LEFT JOIN -> NULL rolname). See tables.sql for the shared aclexplode rationale.
    (
        SELECT
	    COALESCE(jsonb_agg(jsonb_build_object('grantee', COALESCE(gr.rolname, 'PUBLIC'), 'privilege',
		acl.privilege_type, 'grantable', acl.is_grantable)), '[]'::jsonb)
        FROM
            aclexplode(d.defaclacl) AS acl
        LEFT JOIN pg_roles gr ON gr.oid = acl.grantee) AS grants,
    -- Built-in baseline for this (object type, role): acldefault with the object type mapped to
    -- its acldefault code ('S'->'s' sequence, 'T'->'t' type; the rest coincide).
    (
        SELECT
	    COALESCE(jsonb_agg(jsonb_build_object('grantee', COALESCE(gr.rolname, 'PUBLIC'),
		'privilege', acl.privilege_type, 'grantable', acl.is_grantable)), '[]'::jsonb)
        FROM
            aclexplode(acldefault(
                    CASE d.defaclobjtype
                    WHEN 'r' THEN
                        'r'
                    WHEN 'S' THEN
                        's'
                    WHEN 'f' THEN
                        'f'
                    WHEN 'T' THEN
                        't'
                    WHEN 'n' THEN
                        'n' END::"char", d.defaclrole)) AS acl
            LEFT JOIN pg_roles gr ON gr.oid = acl.grantee) AS baseline_grants
FROM
    pg_default_acl d
    LEFT JOIN pg_namespace ns ON ns.oid = d.defaclnamespace
WHERE
    -- A schema-scoped rule in a system schema is not user configuration.
    (ns.nspname IS NULL
        OR (ns.nspname NOT LIKE 'pg_%'
            AND ns.nspname <> 'information_schema'))
    -- Extension-ownership exclusion: an extension may ship default-privilege rules, which it
    -- recreates itself.
    --   [x] self leg       -- the rule itself is extension-owned (d.oid)
    --   [x] namespace leg  -- a schema-scoped rule in an extension-owned schema (ns.oid)
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend dep
        WHERE
            dep.classid = 'pg_default_acl'::regclass
            AND dep.objid = d.oid
            AND dep.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend dep
        WHERE
            dep.objid = ns.oid
            AND dep.deptype = 'e')
ORDER BY
    ROLE,
    schema_name,
    object_type;
