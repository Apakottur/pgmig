-- Row-level security policies (pg_policy), owned by a table.
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pol.polname AS policy_name,
    pol.polcmd::text AS policy_command,
    pol.polpermissive AS policy_permissive,
    -- Role names the policy applies to. polroles = {0} is the PUBLIC pseudo-role, rendered as
    -- an empty list (PUBLIC is the default, so the TO clause is then omitted). Otherwise resolve
    -- each role OID to its name and sort for stable, order-independent output.
    CASE WHEN pol.polroles = '{0}'::oid[] THEN
        ARRAY[]::text[]
    ELSE
        ARRAY (
            SELECT
                pg_get_userbyid(roleid)
            FROM
                unnest(pol.polroles) AS roleid
            ORDER BY
                pg_get_userbyid(roleid))
    END AS policy_roles,
    -- USING and WITH CHECK expressions (NULL when the policy omits them).
    pg_get_expr(pol.polqual, pol.polrelid) AS policy_using,
    pg_get_expr(pol.polwithcheck, pol.polrelid) AS policy_check,
    obj_description(pol.oid, 'pg_policy') AS policy_comment
FROM
    pg_policy pol
    JOIN pg_class c ON c.oid = pol.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind IN ('r', 'p')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion (namespace + owning table); mirrors triggers.sql. A policy
    -- itself is not independently extension-owned, so the owning-table leg already covers it.
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
                d.objid = c.oid
                AND d.deptype = 'e')
        ORDER BY
            n.nspname,
            c.relname,
            pol.polname;
