-- Functions and procedures (excluding aggregates, window functions, and extension-owned ones).
SELECT
    n.nspname AS schema_name,
    p.proname AS func_name,
    pg_get_function_identity_arguments(p.oid) AS func_args,
    pg_get_functiondef(p.oid) AS func_def,
    format_type(p.prorettype, NULL) AS func_rettype,
    p.prokind AS func_kind,
    obj_description(p.oid, 'pg_proc') AS func_comment,
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
