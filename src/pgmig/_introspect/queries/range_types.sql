-- Range types (user range types only; extension-owned ones are excluded). The multirange type
-- Postgres auto-creates alongside every range is not modelled: it is created and dropped with
-- its range, so it never appears in the diff.
--
-- Each optional clause is computed as the exact text to emit (already quoted/qualified) or NULL
-- when the range does not carry it, so the diff renders CREATE TYPE without re-deriving defaults:
--   subtype_opclass -- only when the operator class is not the subtype's default (omitting it
--                      then makes Postgres pick that same default, keeping the round-trip stable).
--   collation       -- only when the range carries an explicit collation that differs from the
--                      subtype's own default collation.
--   subtype_diff    -- the function name when rngsubdiff is set (0 means none).
-- rngcanonical is deliberately not modelled: a user range's canonical function has to be written
-- in C (it takes and returns the range type, which cannot exist when the function is declared), so
-- it is vanishingly rare and cannot round-trip here. A range that carries one is created without a
-- CANONICAL clause -- an accepted first-cut limitation.
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    format_type(r.rngsubtype, NULL) AS subtype,
    CASE WHEN NOT oc.opcdefault THEN
        format('%I.%I', ocn.nspname, oc.opcname)
    END AS subtype_opclass,
    CASE WHEN r.rngcollation <> 0
        AND r.rngcollation <> st.typcollation THEN
        format('%I.%I', cn.nspname, col.collname)
    END AS collation,
    CASE WHEN r.rngsubdiff <> 0 THEN
        r.rngsubdiff::regproc::text
    END AS subtype_diff,
    obj_description(t.oid, 'pg_type') AS type_comment,
    pg_get_userbyid(t.typowner) AS type_owner
FROM
    pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    JOIN pg_range r ON r.rngtypid = t.oid
    JOIN pg_type st ON st.oid = r.rngsubtype
    JOIN pg_opclass oc ON oc.oid = r.rngsubopc
    JOIN pg_namespace ocn ON ocn.oid = oc.opcnamespace
    LEFT JOIN pg_collation col ON col.oid = r.rngcollation
    LEFT JOIN pg_namespace cn ON cn.oid = col.collnamespace
WHERE
    t.typtype = 'r'
    AND n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    -- Extension-ownership exclusion checklist (see the sibling queries: every query must
    -- carry all applicable legs or the loader KeyErrors on an object left in the model
    -- whose owner was dropped):
    --   [x] namespace leg  -- range type in an extension-owned schema (n.oid)
    --   [x] self leg       -- the range type itself is extension-owned (t.oid)
    --   [ ] owning-table leg -- n/a, a range type is not attached to a table
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
