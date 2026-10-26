-- Event triggers (pg_event_trigger, CREATE EVENT TRIGGER). Database-global: they have no schema
-- of their own, so each row carries the schema of the function the trigger executes, which the
-- loader uses for --ignore-schema (the trigger cannot exist without its function).
SELECT
    e.evtname AS trigger_name,
    e.evtevent AS event,
    -- The WHEN TAG IN filter, sorted so the same tags listed in another order compare equal;
    -- empty when the trigger has no filter (evttags is NULL).
    COALESCE((
        SELECT
            array_agg(tag ORDER BY tag)
        FROM unnest(e.evttags) AS tag), '{}') AS tags,
    n.nspname AS function_schema,
    p.proname AS function_name,
    e.evtenabled AS enabled,
    pg_get_userbyid(e.evtowner) AS owner,
    obj_description(e.oid, 'pg_event_trigger') AS comment
FROM
    pg_event_trigger e
    JOIN pg_proc p ON p.oid = e.evtfoid
    JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE
    -- Extension-owned event triggers are recreated by their extension.
    NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.classid = 'pg_event_trigger'::regclass
            AND d.objid = e.oid
            AND d.deptype = 'e')
ORDER BY
    e.evtname;
