-- Unsupported object kinds. None are modelled yet, so their presence must raise rather
-- than let generate() return "" and falsely claim convergence. Each leg mirrors the
-- filter that drops the kind from a sibling loader query, so nothing slips through both.
-- Every leg emits (schema_name, obj_name, catalog, kind); unsupported.py keys the display
-- name on (catalog, kind), so the same code may recur across catalogs. kind is cast to text
-- because relkind/typtype/... are the 1-byte "char" type, which would truncate the synthetic
-- multi-char labels ('rls', 'inherits') in the UNION.
--   pg_class:             foreign table 'f'; row-level-security table 'rls'; legacy
--                         inheritance child 'inherits'.
--   pg_type:              range 'r'; base type 'b'.
--   pg_constraint:        exclusion 'x'   (dropped by constraints.sql's contype filter).
--   pg_proc:              aggregate 'a', window 'w'   (dropped by functions.sql's prokind filter).
--   pg_trigger:           INSTEAD OF trigger on a view 'v'   (dropped by triggers.sql).
--   pg_rewrite:           rule 'r'   (the view _RETURN rule is excluded).
--   pg_policy:            row-level-security policy 'p'.
--   pg_statistic_ext:     extended statistics 'e'.
--   pg_event_trigger:     event trigger 'e' (database-global, no schema).
-- Extension-owned objects are excluded (the extension recreates them). Drop a kind from
-- a filter as its roadmap feature lands.
SELECT
    n.nspname AS schema_name,
    c.relname AS obj_name,
    'pg_class' AS catalog,
    c.relkind::text AS kind
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind = 'f'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
SELECT
    n.nspname AS schema_name,
    t.typname AS obj_name,
    'pg_type' AS catalog,
    t.typtype::text AS kind
FROM
    pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE
    t.typtype = 'r'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- Exclusion constraints ('x'), dropped by constraints.sql's contype filter. Same
-- conparentid = 0 guard as constraints.sql so a partition-inherited copy is not
-- double-reported alongside the parent declaration.
SELECT
    n.nspname AS schema_name,
    con.conname AS obj_name,
    'pg_constraint' AS catalog,
    con.contype::text AS kind
FROM
    pg_constraint con
    JOIN pg_class c ON c.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    con.contype = 'x'
    AND c.relkind IN ('r', 'p')
    AND con.conparentid = 0
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- Aggregate ('a') and window ('w') functions, dropped by functions.sql's prokind filter.
SELECT
    n.nspname AS schema_name,
    p.proname AS obj_name,
    'pg_proc' AS catalog,
    p.prokind::text AS kind
FROM
    pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE
    p.prokind IN ('a', 'w')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- INSTEAD OF triggers on views (relkind 'v'), excluded by triggers.sql's relkind filter.
-- Same NOT tgisinternal / tgparentid = 0 guards as triggers.sql.
SELECT
    n.nspname AS schema_name,
    t.tgname AS obj_name,
    'pg_trigger' AS catalog,
    'v' AS kind
FROM
    pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    NOT t.tgisinternal
    AND c.relkind = 'v'
    AND t.tgparentid = 0
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- Rules (pg_rewrite). The auto _RETURN rule backing every view is excluded; every other
-- rule is a user CREATE RULE that is not modelled.
SELECT
    n.nspname AS schema_name,
    r.rulename AS obj_name,
    'pg_rewrite' AS catalog,
    'r' AS kind
FROM
    pg_rewrite r
    JOIN pg_class c ON c.oid = r.ev_class
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    r.rulename <> '_RETURN'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- Row-level security policies (pg_policy). CREATE POLICY objects are not modelled.
SELECT
    n.nspname AS schema_name,
    pol.polname AS obj_name,
    'pg_policy' AS catalog,
    'p' AS kind
FROM
    pg_policy pol
    JOIN pg_class c ON c.oid = pol.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- Tables with row-level security enabled or forced (pg_class.relrowsecurity /
-- relforcerowsecurity). This changes access semantics even with no policy, and is not
-- modelled. The kind is a synthetic label ('rls'), not a relkind, so it never collides
-- with another pg_class leg such as the foreign-table one.
SELECT
    n.nspname AS schema_name,
    c.relname AS obj_name,
    'pg_class' AS catalog,
    'rls' AS kind
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE (c.relrowsecurity
    OR c.relforcerowsecurity)
AND c.relkind IN ('r', 'p')
AND n.nspname NOT LIKE 'pg_%'
AND n.nspname <> 'information_schema'
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
UNION ALL
-- User base types (pg_type typtype 'b'). The auto array type of every user type is also
-- typtype 'b' but has typcategory 'A'; excluding that leaves only genuine CREATE TYPE
-- base types (built-in scalars live in pg_catalog, already excluded by the namespace leg).
SELECT
    n.nspname AS schema_name,
    t.typname AS obj_name,
    'pg_type' AS catalog,
    'b' AS kind
FROM
    pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE
    t.typtype = 'b'
    AND t.typcategory <> 'A'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- Legacy inheritance children: an ordinary table (relkind 'r') that inherits from another
-- ordinary table. These load as standalone tables and lose the INHERITS clause on re-emit.
-- Partition children have a partitioned parent (relkind 'p') and are handled by partitioned
-- support, so the parent-relkind filter excludes them. EXISTS reports a child once even if
-- it inherits several parents. The kind is a synthetic label, not a relkind.
SELECT
    n.nspname AS schema_name,
    c.relname AS obj_name,
    'pg_class' AS catalog,
    'inherits' AS kind
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE
    c.relkind = 'r'
    AND EXISTS (
        SELECT
            1
        FROM
            pg_inherits i
            JOIN pg_class pc ON pc.oid = i.inhparent
        WHERE
            i.inhrelid = c.oid
            AND pc.relkind = 'r')
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- Extended statistics (pg_statistic_ext, CREATE STATISTICS). Not modelled.
SELECT
    n.nspname AS schema_name,
    s.stxname AS obj_name,
    'pg_statistic_ext' AS catalog,
    'e' AS kind
FROM
    pg_statistic_ext s
    JOIN pg_namespace n ON n.oid = s.stxnamespace
    JOIN pg_class c ON c.oid = s.stxrelid
WHERE
    n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
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
UNION ALL
-- Event triggers (pg_event_trigger, CREATE EVENT TRIGGER). Database-global: they have no
-- schema, so schema_name is NULL and only the self extension-ownership leg applies.
SELECT
    NULL::text AS schema_name,
    e.evtname AS obj_name,
    'pg_event_trigger' AS catalog,
    'e' AS kind
FROM
    pg_event_trigger e
WHERE
    NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = e.oid
            AND d.deptype = 'e')
ORDER BY
    schema_name,
    obj_name;
