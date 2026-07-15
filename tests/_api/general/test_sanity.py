from tests._api.generate_setup import GenerateSetup


async def test_generate_sanity(gen_setup: GenerateSetup) -> None:
    """
    Sanity test - no SQL is run on either DB so no migration SQL is generated.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[],
        diff=[],
    )
