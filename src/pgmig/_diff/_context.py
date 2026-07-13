from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from pgmig._models import DbInfo


@dataclass(frozen=True)
class _ContextData:
    """
    Everything a generator needs: the two databases being diffed and the output
    configuration. The immutable value stored in the context var; generators read it through
    the `context` proxy rather than receiving it as an argument.
    """

    # Databases.
    source: DbInfo
    target: DbInfo

    # Output configuration.

    # Whether to emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with CONCURRENTLY.
    # Using CONCURRENTLY avoid blocking index read/write operations, but takes longer to execute and cannot be
    # run inside a transaction block.
    index_concurrently: bool = False

    # Names of extensions whose version mismatch is ignored: no ALTER EXTENSION ... UPDATE TO
    # is emitted for them. Empty (default) ignores none.
    ignore_extension_version: Sequence[str] = ()


# The current diff's data. No default: reading it outside an active `use_context` block raises
# LookupError, which surfaces the misuse loudly instead of silently diffing nothing.
_context: ContextVar[_ContextData] = ContextVar("pgmig_context")


class _Context:
    """
    Proxy over the context var. Generators import the `context` singleton and read
    `context.source` etc.; each access fetches the value set for the running diff.
    """

    @property
    def source(self) -> DbInfo:
        return _context.get().source

    @property
    def target(self) -> DbInfo:
        return _context.get().target

    @property
    def index_concurrently(self) -> bool:
        return _context.get().index_concurrently

    @property
    def ignore_extension_version(self) -> Sequence[str]:
        return _context.get().ignore_extension_version


context = _Context()


@contextmanager
def use_context(data: _ContextData) -> Iterator[None]:
    """
    Bind `data` as the current diff context for the duration of the block, restoring the
    previous value on exit. Reentrant: nested calls stack via the reset token.
    """
    token = _context.set(data)
    try:
        yield
    finally:
        _context.reset(token)
