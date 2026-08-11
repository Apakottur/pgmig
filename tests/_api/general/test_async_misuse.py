import pytest

import pgmig


async def test_generate_from_running_loop_raises() -> None:
    """Calling generate() from within an asyncio context should guide the user to use agenerate() instead."""
    with pytest.raises(pgmig.PgmigApiError, match="agenerate"):
        pgmig.generate(source="postgresql://unused", target="postgresql://unused")
