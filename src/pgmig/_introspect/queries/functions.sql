-- Functions and procedures (excluding aggregates, window functions, and extension-owned ones).
SELECT
    n.nspname AS schema_name,
    p.proname AS func_name,
    pg_get_function_identity_arguments(p.oid) AS func_args,
    pg_get_functiondef(p.oid) AS func_def,
    format_type(p.prorettype, NULL) AS func_rettype,
    p.prokind AS func_kind,
    obj_description(p.oid, 'pg_proc') AS func_comment,
    pg_get_userbyid(p.proowner) AS func_owner,
    -- Effective ACL as a set of (grantee, privilege, grantable). A NULL proacl means the owner
    -- default, expanded via acldefault('f', owner) -- which grants EXECUTE to PUBLIC, so a
    -- REVOKE EXECUTE ... FROM PUBLIC surfaces as a diff. See tables.sql for the full rationale.
    (
        SELECT
	    COALESCE(jsonb_agg(jsonb_build_object('grantee', COALESCE(gr.rolname, 'PUBLIC'), 'privilege',
		acl.privilege_type, 'grantable', acl.is_grantable)), '[]'::jsonb)
        FROM
            aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) AS acl
        LEFT JOIN pg_roles gr ON gr.oid = acl.grantee) AS func_grants,
    EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.refclassid = 'pg_proc'::regclass
            AND d.refobjid = p.oid
            AND d.deptype IN ('n', 'a')
            AND d.classid <> 'pg_trigger'::regclass) AS func_has_dependents,
    -- The non-trigger objects that depend on this routine (same pg_depend rows as
    -- func_has_dependents), each resolved to a structured identity by dependent catalog
    -- (classid). Drives the recreate-around-dependents path on a return-type change:
    --   pg_attrdef   -> a column default ('default'): its table and column.
    --   pg_constraint-> a check/other constraint ('constraint'): its table and name.
    --   pg_class (i) -> an expression index ('index'): its table and index name.
    --   pg_proc      -> another routine ('routine'): only its name (chains are unsupported).
    --   anything else-> 'other', carrying the catalog name for the error message.
    COALESCE((
        SELECT
            jsonb_agg(DISTINCT dep_obj.dep)
        FROM pg_depend d
    LEFT JOIN pg_attrdef ad ON d.classid = 'pg_attrdef'::regclass
        AND ad.oid = d.objid
    LEFT JOIN pg_class adrel ON adrel.oid = ad.adrelid
    LEFT JOIN pg_namespace adns ON adns.oid = adrel.relnamespace
    LEFT JOIN pg_attribute ada ON ada.attrelid = ad.adrelid
        AND ada.attnum = ad.adnum
    LEFT JOIN pg_constraint con ON d.classid = 'pg_constraint'::regclass
        AND con.oid = d.objid
    LEFT JOIN pg_class conrel ON conrel.oid = con.conrelid
    LEFT JOIN pg_namespace conns ON conns.oid = conrel.relnamespace
    LEFT JOIN pg_class idx ON d.classid = 'pg_class'::regclass
        AND idx.oid = d.objid
        AND idx.relkind = 'i'
    LEFT JOIN pg_namespace idxns ON idxns.oid = idx.relnamespace
    LEFT JOIN pg_index idxi ON idxi.indexrelid = idx.oid
    LEFT JOIN pg_class idxtbl ON idxtbl.oid = idxi.indrelid
    LEFT JOIN pg_proc dp ON d.classid = 'pg_proc'::regclass
        AND dp.oid = d.objid
    LEFT JOIN pg_namespace dpns ON dpns.oid = dp.pronamespace
    CROSS JOIN LATERAL (
        SELECT
            CASE WHEN ad.oid IS NOT NULL THEN
		jsonb_build_object('kind', 'default', 'schema_name', adns.nspname, 'table',
		    adrel.relname, 'name', ada.attname)
            WHEN con.oid IS NOT NULL THEN
		jsonb_build_object('kind', 'constraint', 'schema_name', conns.nspname, 'table',
		    conrel.relname, 'name', con.conname)
            WHEN idx.oid IS NOT NULL THEN
		jsonb_build_object('kind', 'index', 'schema_name', idxns.nspname, 'table',
		    idxtbl.relname, 'name', idx.relname)
            WHEN dp.oid IS NOT NULL THEN
		jsonb_build_object('kind', 'routine', 'schema_name', dpns.nspname, 'table',
		    '', 'name', dp.proname)
            ELSE
		jsonb_build_object('kind', 'other', 'schema_name', n.nspname, 'table',
		    '', 'name', d.classid::regclass::text)
            END AS dep) dep_obj
    WHERE
        d.refclassid = 'pg_proc'::regclass
        AND d.refobjid = p.oid
        AND d.deptype IN ('n', 'a')
        AND d.classid <> 'pg_trigger'::regclass), '[]'::jsonb) AS func_dependents,
    -- Forward function -> function hard dependencies (deptype 'n'), as {schema_name, name,
    -- args} objects; used to order drops so a routine is dropped before the ones it depends on.
    COALESCE((
        SELECT
	    jsonb_agg(jsonb_build_object('schema_name', rn.nspname, 'name', rp.proname, 'args',
		pg_get_function_identity_arguments(rp.oid)))
        FROM pg_depend d
        JOIN pg_proc rp ON rp.oid = d.refobjid
        JOIN pg_namespace rn ON rn.oid = rp.pronamespace
        WHERE
            d.classid = 'pg_proc'::regclass
            AND d.objid = p.oid
            AND d.refclassid = 'pg_proc'::regclass
            AND d.deptype = 'n'), '[]'::jsonb) AS func_depends_on_functions,
    -- Forward function -> relation hard dependencies (deptype 'n'), as {schema_name, name}
    -- objects; used to refuse a late drop that is circular with a relation dropped the same run.
    COALESCE((
        SELECT
            jsonb_agg(jsonb_build_object('schema_name', rn.nspname, 'name', rc.relname))
        FROM pg_depend d
        JOIN pg_class rc ON rc.oid = d.refobjid
        JOIN pg_namespace rn ON rn.oid = rc.relnamespace
        WHERE
            d.classid = 'pg_proc'::regclass
            AND d.objid = p.oid
            AND d.refclassid = 'pg_class'::regclass
            AND d.deptype = 'n'
	    AND rc.relkind IN ('r', 'p', 'v', 'm')),
		'[]'::jsonb) AS func_depends_on_relations
FROM
    pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE
    p.prokind IN ('f', 'p')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- function in an extension-owned schema (n.oid)
    --   [x] self leg       -- the function itself is extension-owned (p.oid)
    --   [ ] owning-table leg -- n/a, functions are not attached to a table
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
    -- Exclude the constructor functions Postgres auto-creates for a range/multirange type
    -- (e.g. r_int(integer, integer), r_int_multirange(...)): they carry an internal ('i')
    -- dependency on the type and are created and dropped with it, so diffing them as
    -- standalone routines would double-emit against the range-type diff.
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.classid = 'pg_proc'::regclass
            AND d.objid = p.oid
            AND d.refclassid = 'pg_type'::regclass
            AND d.deptype = 'i')
ORDER BY
    n.nspname,
    p.proname,
    func_args;
