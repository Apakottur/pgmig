-- User dependency edges (pg_depend) that cross a schema boundary: an object in one user schema
-- depending on an object in a different user schema. Used only when --ignore-schema is set, to
-- refuse ignoring a schema that is connected to a kept one.
--
-- Each endpoint's schema is pg_identify_object's schema, falling back to the owning relation's
-- schema for a schema-less sub-object (a rewrite rule backs a view's reads, and a trigger /
-- column default / policy belongs to a table -- none carry their own schema). One query then
-- covers every dependency kind (foreign keys, view/matview reads via the _RETURN rule, function
-- bodies, cross-schema column types, OWNED BY) without per-kind logic.
--
-- Only normal ('n') and auto ('a') dependencies are user connections; internal ('i'), extension
-- ('e') and pin ('p') edges are an object's own machinery. System schemas on either side are
-- excluded (a dependency on a built-in type lives in pg_catalog, not a user-schema link).
SELECT
    obj.schema AS obj_schema,
    obj.identity AS obj_identity,
    ref.schema AS ref_schema,
    ref.identity AS ref_identity
FROM
    pg_depend d
    CROSS JOIN LATERAL (
        SELECT
            COALESCE(io.schema, owner.nspname) AS schema,
            io.identity AS IDENTITY
        FROM
            pg_identify_object (d.classid, d.objid, d.objsubid) AS io
            LEFT JOIN LATERAL (
                SELECT
                    n.nspname
                FROM
                    pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE
                    c.oid = CASE d.classid
                    WHEN 'pg_rewrite'::regclass THEN
                    (
                        SELECT
                            ev_class
                        FROM
                            pg_rewrite
                        WHERE
                            oid = d.objid)
                    WHEN 'pg_trigger'::regclass THEN
                    (
                        SELECT
                            tgrelid
                        FROM
                            pg_trigger
                        WHERE
                            oid = d.objid)
                    WHEN 'pg_attrdef'::regclass THEN
                    (
                        SELECT
                            adrelid
                        FROM
                            pg_attrdef
                        WHERE
                            oid = d.objid)
                    WHEN 'pg_policy'::regclass THEN
                    (
                        SELECT
                            polrelid
                        FROM
                            pg_policy
                        WHERE
                            oid = d.objid)
                    END) AS owner ON TRUE) AS obj
    CROSS JOIN LATERAL (
        SELECT
            COALESCE(io.schema, owner.nspname) AS schema,
            io.identity AS IDENTITY
        FROM
            pg_identify_object (d.refclassid, d.refobjid, d.refobjsubid) AS io
            LEFT JOIN LATERAL (
                SELECT
                    n.nspname
                FROM
                    pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE
                    c.oid = CASE d.refclassid
                    WHEN 'pg_rewrite'::regclass THEN
                    (
                        SELECT
                            ev_class
                        FROM
                            pg_rewrite
                        WHERE
                            oid = d.refobjid)
                    WHEN 'pg_trigger'::regclass THEN
                    (
                        SELECT
                            tgrelid
                        FROM
                            pg_trigger
                        WHERE
                            oid = d.refobjid)
                    WHEN 'pg_attrdef'::regclass THEN
                    (
                        SELECT
                            adrelid
                        FROM
                            pg_attrdef
                        WHERE
                            oid = d.refobjid)
                    WHEN 'pg_policy'::regclass THEN
                    (
                        SELECT
                            polrelid
                        FROM
                            pg_policy
                        WHERE
                            oid = d.refobjid)
                    END) AS owner ON TRUE) AS ref
WHERE
    d.deptype IN ('n', 'a')
    AND obj.schema IS NOT NULL
    AND ref.schema IS NOT NULL
    AND obj.schema <> ref.schema
    AND obj.schema NOT LIKE 'pg_%'
    AND obj.schema <> 'information_schema'
    AND ref.schema NOT LIKE 'pg_%'
    AND ref.schema <> 'information_schema';
