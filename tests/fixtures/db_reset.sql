-- Reset a database to the state of a freshly created one, on an open connection -- no
-- DROP/CREATE DATABASE round-trip and no reconnect. Reused across tests on a persistent
-- connection, this is roughly an order of magnitude faster than dropping and recreating.
--
-- It drops the object classes the tests exercise: schemas, extensions, and per-database
-- settings. Global objects (roles, tablespaces) are never created by the tests. If a future
-- test leaks state this misses, extend this file and add a test covering it.
DO $$
DECLARE
    entry record;
BEGIN
    -- Clear per-database settings a test may have pinned (e.g. ALTER DATABASE ... SET search_path).
    EXECUTE format('ALTER DATABASE %I RESET ALL', current_database());
    -- Drop extensions before schemas: an extension living in a custom schema blocks
    -- DROP SCHEMA on that schema until the extension itself is gone.
    FOR entry IN
    SELECT
        extname
    FROM
        pg_extension
    WHERE
        extname <> 'plpgsql' LOOP
            EXECUTE format('DROP EXTENSION %I CASCADE', entry.extname);
        END LOOP;
    -- Drop every non-system schema; CASCADE removes the objects inside them.
    FOR entry IN
    SELECT
        nspname
    FROM
        pg_namespace
    WHERE
        nspname NOT LIKE 'pg_%'
        AND nspname NOT IN ('information_schema', 'public')
        LOOP
            EXECUTE format('DROP SCHEMA %I CASCADE', entry.nspname);
        END LOOP;
END
$$;

-- Recreate a pristine public schema, matching a freshly created database (including the
-- default comment, whose absence would otherwise show up as a diff).
DROP SCHEMA public CASCADE;

CREATE SCHEMA public;

COMMENT ON SCHEMA public IS 'standard public schema';
