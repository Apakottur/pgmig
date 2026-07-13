from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from pgmig._models import DbInfo


@dataclass(frozen=True)
class _ContextData:
    """
    Context data for the current diff generation.
    """

    # Databases.
    source: DbInfo
    target: DbInfo

    # Whether to emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with CONCURRENTLY.
    # Using CONCURRENTLY avoid blocking index read/write operations, but takes longer to execute and cannot be
    # run inside a transaction block.
    index_concurrently: bool

    # Names of extensions whose version mismatch is ignored: no ALTER EXTENSION ... UPDATE TO
    # is emitted for them. Empty (default) ignores none.
    ignore_extension_version: Sequence[str]


# Context of the current diff generation.
_context: ContextVar[_ContextData] = ContextVar("pgmig_context")


class _Context:
    """
    Proxy over the context var. Generators import the `context` singleton and read
    `context.source` etc.; each access fetches the value set for the running diff.
    """

    @contextmanager
    def context_scope(
        self,
        *,
        source: DbInfo,
        target: DbInfo,
        index_concurrently: bool,
        ignore_extension_version: Sequence[str],
    ) -> Iterator[None]:
        token = _context.set(
            _ContextData(
                source=source,
                target=target,
                index_concurrently=index_concurrently,
                ignore_extension_version=ignore_extension_version,
            )
        )
        try:
            yield
        finally:
            _context.reset(token)

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
