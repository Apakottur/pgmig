FROM postgres:18.4-alpine3.24

# This Postgres instance only ever holds ephemeral test data: the databases are
# dropped and recreated per test and the whole container is disposable. So we
# trade crash-durability for speed - DROP/CREATE DATABASE otherwise force
# fsync/checkpoints and dominate the test runtime. None of these are safe for
# real data.
#
#   fsync=off               Don't force writes to physical disk. A crash can
#                           corrupt the cluster - fine, it's throwaway.
#   synchronous_commit=off  COMMIT returns before the WAL is flushed to disk. A
#                           crash may lose the latest commits; the DB stays
#                           internally consistent.
#   full_page_writes=off    Skip full-page images in the WAL (torn-page
#                           protection). Redundant once fsync is off; trims WAL
#                           write work.
CMD ["postgres", "-c", "fsync=off", "-c", "synchronous_commit=off", "-c", "full_page_writes=off"]
