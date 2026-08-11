import shutil
import sys
import textwrap

from pgmig._errors import DbConnectionError, DbDriverError, _PgmigError

# Layout of the box that sets verbatim third-party output apart from pgmig's own message.
_BOX_INDENT = "  "
_BOX_MAX_WIDTH = 100
_BOX_UNICODE = ("╭", "╰", "─", "│")
_BOX_ASCII = ("+", "+", "-", "|")


def _format_db_driver_error(label: str, error: DbDriverError | None) -> list[str]:
    """
    Format a database driver error.
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
    for line in str(error.driver_error).splitlines():
        wrapped = textwrap.wrap(
            line,
            width=body_width,
            break_long_words=False,
            break_on_hyphens=False,
            subsequent_indent="    ",
        )
        # An empty line wraps to nothing; keep it, it is part of the driver's own layout.
        body.extend(wrapped or [""])

    header = f"{top_left}{horizontal} {error.driver.resolved} "
    return [
        f"{_BOX_INDENT}{label} - UNREACHABLE",
        f"{indent}{header}{horizontal * max(body_width + 2 - len(header), 0)}",
        *(f"{indent}{vertical} {line}".rstrip() for line in body),
        f"{indent}{bottom_left}{horizontal * (body_width + 1)}",
    ]


def _format_db_connection_error(error: DbConnectionError) -> str:
    return "\n".join(
        [
            f"\n{error.message}:",
            *_format_db_driver_error("Source", error.source_error),
            *_format_db_driver_error("Target", error.target_error),
        ]
    )


def format_error(error: _PgmigError) -> str:
    """
    Format an error to be displayed to the user.
    """
    match error:
        case DbConnectionError():
            return _format_db_connection_error(error)
        # Default formatting.
        case _:
            return error.message
