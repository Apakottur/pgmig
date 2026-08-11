import shutil
import sys
import textwrap

from pgmig._drivers import DbDriver
from pgmig._errors import DbConnectionError, _PgmigError

# Layout of the box that sets verbatim third-party output apart from pgmig's own message.
_BOX_INDENT = "  "
_BOX_MAX_WIDTH = 100
_BOX_UNICODE = ("╭", "╰", "─", "│")
_BOX_ASCII = ("+", "+", "-", "|")


def _format_database(label: str, error: BaseException | None, *, driver: DbDriver) -> list[str]:
    """
    One database's line in a connection report, followed by the driver's own words quoted in
    a box when it is the one that failed, so they do not read as more of pgmig's message.
    """
    if error is None:
        return [f"{_BOX_INDENT}{label} - REACHABLE"]

    # Box-drawing characters, downgraded to ASCII when the error stream cannot encode them
    # (e.g. output redirected under a legacy Windows code page), where drawing the nicer box
    # would raise on top of the error being reported.
    try:
        "".join(_BOX_UNICODE).encode(sys.stderr.encoding or "ascii")
    except UnicodeEncodeError:
        top_left, bottom_left, horizontal, vertical = _BOX_ASCII
    else:
        top_left, bottom_left, horizontal, vertical = _BOX_UNICODE

    # Leave room for the indent and the "| " prefix. Long words (a DSN, a URL) are left to
    # overflow rather than be chopped mid-token: the box has no right edge to breach.
    indent = _BOX_INDENT * 2
    width = min(shutil.get_terminal_size(fallback=(_BOX_MAX_WIDTH, 24)).columns, _BOX_MAX_WIDTH)
    body_width = width - len(indent) - 2

    body = []
    for line in str(error).splitlines():
        wrapped = textwrap.wrap(
            line,
            width=body_width,
            break_long_words=False,
            break_on_hyphens=False,
            subsequent_indent="    ",
        )
        # An empty line wraps to nothing; keep it, it is part of the driver's own layout.
        body.extend(wrapped or [""])

    header = f"{top_left}{horizontal} {driver.resolved} "
    return [
        f"{_BOX_INDENT}{label} - UNREACHABLE",
        f"{indent}{header}{horizontal * max(body_width + 2 - len(header), 0)}",
        *(f"{indent}{vertical} {line}".rstrip() for line in body),
        f"{indent}{bottom_left}{horizontal * (body_width + 1)}",
    ]


def format_error(error: _PgmigError, *, driver: DbDriver) -> str:
    """
    Render a known error for the terminal. A failure to connect reports both databases the
    run needed, with the driver's own words quoted in a box under the one that failed.
    """
    if not isinstance(error, DbConnectionError):
        return error.message

    # Set the report off from whatever the terminal printed before it, and lead into the
    # per-database lines below.
    return "\n".join(
        [
            f"\n{error.message}:",
            *_format_database("Source", error.source_error, driver=driver),
            *_format_database("Target", error.target_error, driver=driver),
        ]
    )
