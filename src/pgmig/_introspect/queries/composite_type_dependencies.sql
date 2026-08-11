-- Dependencies among standalone composite types: a user composite type with a field whose
-- type -- or, for an array field, whose element type -- is another standalone composite type.
-- CREATE TYPE ... AS (...) must run after the types its fields reference, and DROP before the
-- types it references; a composite-on-composite field means ordering the create/drop needs a
-- topological sort within the type phases (see composite_type_dependencies.py load). A field of
-- a base type, enum, or domain is fine (those are created before, and dropped after, the
-- composite-type phase by generator order).
SELECT DISTINCT
    dependent_ns.nspname AS dependent_schema,
    dependent_t.typname AS dependent_type,
    referenced_ns.nspname AS referenced_schema,
    referenced_t.typname AS referenced_type
FROM
    pg_type dependent_t
    JOIN pg_namespace dependent_ns ON dependent_ns.oid = dependent_t.typnamespace
    JOIN pg_class dependent_c ON dependent_c.oid = dependent_t.typrelid
    JOIN pg_attribute a ON a.attrelid = dependent_t.typrelid
        AND a.attnum > 0
        AND NOT a.attisdropped
    JOIN pg_type field_t ON field_t.oid = a.atttypid
    -- Resolve an array field to its element type (a_point[] -> a_point); a scalar field
    -- resolves to itself.
    JOIN pg_type referenced_t ON referenced_t.oid = CASE WHEN field_t.typcategory = 'A' THEN
        field_t.typelem
    ELSE
        field_t.oid
    END
    JOIN pg_namespace referenced_ns ON referenced_ns.oid = referenced_t.typnamespace
    JOIN pg_class referenced_c ON referenced_c.oid = referenced_t.typrelid
WHERE
    dependent_t.typtype = 'c'
    AND dependent_c.relkind = 'c'
    AND referenced_t.typtype = 'c'
    AND referenced_c.relkind = 'c'
    AND dependent_t.oid <> referenced_t.oid
    -- Only edges among managed objects belong here: an edge to a type pgmig does not model
    -- (one in a system schema, or an extension-owned one) is bogus state that would mislead
    -- the ordering logic. Exclude, on each side, what composite_types.sql excludes from the
    -- model:
    --   [x] system-schema leg -- pg_catalog / information_schema (nspname)
    --   [x] namespace leg      -- type in an extension-owned schema (*_ns.oid)
    --   [x] self leg           -- the type itself is extension-owned (dependent/referenced_t.oid)
    AND dependent_ns.nspname NOT LIKE 'pg_%'
    AND dependent_ns.nspname <> 'information_schema'
    AND referenced_ns.nspname NOT LIKE 'pg_%'
    AND referenced_ns.nspname <> 'information_schema'
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend ed
        WHERE
            ed.objid = dependent_ns.oid
            AND ed.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend ed
        WHERE
            ed.objid = dependent_t.oid
            AND ed.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend ed
        WHERE
            ed.objid = referenced_ns.oid
            AND ed.deptype = 'e')
    AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend ed
        WHERE
            ed.objid = referenced_t.oid
            AND ed.deptype = 'e')
ORDER BY
    dependent_schema,
    dependent_type,
    referenced_schema,
    referenced_type;
