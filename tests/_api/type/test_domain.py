from tests._api.generate_setup import GenerateSetup


async def test_domain_create(gen_setup: GenerateSetup) -> None:
    """
    Domain present in target but missing in source -> CREATE DOMAIN.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE DOMAIN age AS integer"],
        diff=['CREATE DOMAIN "public"."age" AS integer'],
    )


async def test_domain_create_with_default_not_null_and_check(gen_setup: GenerateSetup) -> None:
    """
    A created domain renders DEFAULT and NOT NULL inline and each CHECK as a separate
    ALTER DOMAIN ADD CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE DOMAIN positive_int AS integer DEFAULT 1 NOT NULL CONSTRAINT positive_int_check CHECK (VALUE > 0)"
        ],
        diff=[
            'CREATE DOMAIN "public"."positive_int" AS integer DEFAULT 1 NOT NULL',
            'ALTER DOMAIN "public"."positive_int" ADD CONSTRAINT "positive_int_check" CHECK ((VALUE > 0))',
        ],
    )


async def test_domain_drop(gen_setup: GenerateSetup) -> None:
    """
    Domain present in source but missing in target -> DROP DOMAIN.
    """
    await gen_setup.assert_diff(
        src=["CREATE DOMAIN age AS integer"],
        dst=[],
        diff=['DROP DOMAIN "public"."age"'],
    )


async def test_domain_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical domain on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE DOMAIN age AS integer DEFAULT 0 CONSTRAINT age_check CHECK (VALUE >= 0)"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_domain_default_changed(gen_setup: GenerateSetup) -> None:
    """
    Same domain, differing default -> ALTER DOMAIN SET DEFAULT.
    """
    await gen_setup.assert_diff(
        src=["CREATE DOMAIN age AS integer DEFAULT 0"],
        dst=["CREATE DOMAIN age AS integer DEFAULT 18"],
        diff=['ALTER DOMAIN "public"."age" SET DEFAULT 18'],
    )


async def test_domain_default_dropped(gen_setup: GenerateSetup) -> None:
    """
    Default present in source but not target -> ALTER DOMAIN DROP DEFAULT.
    """
    await gen_setup.assert_diff(
        src=["CREATE DOMAIN age AS integer DEFAULT 0"],
        dst=["CREATE DOMAIN age AS integer"],
        diff=['ALTER DOMAIN "public"."age" DROP DEFAULT'],
    )


async def test_domain_not_null_set(gen_setup: GenerateSetup) -> None:
    """
    NOT NULL added in target -> ALTER DOMAIN SET NOT NULL.
    """
    await gen_setup.assert_diff(
        src=["CREATE DOMAIN age AS integer"],
        dst=["CREATE DOMAIN age AS integer NOT NULL"],
        diff=['ALTER DOMAIN "public"."age" SET NOT NULL'],
    )


async def test_domain_not_null_dropped(gen_setup: GenerateSetup) -> None:
    """
    NOT NULL removed in target -> ALTER DOMAIN DROP NOT NULL.
    """
    await gen_setup.assert_diff(
        src=["CREATE DOMAIN age AS integer NOT NULL"],
        dst=["CREATE DOMAIN age AS integer"],
        diff=['ALTER DOMAIN "public"."age" DROP NOT NULL'],
    )


async def test_domain_check_added(gen_setup: GenerateSetup) -> None:
    """
    A CHECK present in target only -> ALTER DOMAIN ADD CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=["CREATE DOMAIN age AS integer"],
        dst=["CREATE DOMAIN age AS integer CONSTRAINT age_positive CHECK (VALUE > 0)"],
        diff=['ALTER DOMAIN "public"."age" ADD CONSTRAINT "age_positive" CHECK ((VALUE > 0))'],
    )


async def test_domain_check_dropped(gen_setup: GenerateSetup) -> None:
    """
    A CHECK present in source only -> ALTER DOMAIN DROP CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=["CREATE DOMAIN age AS integer CONSTRAINT age_positive CHECK (VALUE > 0)"],
        dst=["CREATE DOMAIN age AS integer"],
        diff=['ALTER DOMAIN "public"."age" DROP CONSTRAINT "age_positive"'],
    )


async def test_domain_check_renamed(gen_setup: GenerateSetup) -> None:
    """
    Same CHECK definition, different constraint name -> ALTER DOMAIN RENAME CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=["CREATE DOMAIN age AS integer CONSTRAINT age_old CHECK (VALUE > 0)"],
        dst=["CREATE DOMAIN age AS integer CONSTRAINT age_new CHECK (VALUE > 0)"],
        diff=['ALTER DOMAIN "public"."age" RENAME CONSTRAINT "age_old" TO "age_new"'],
    )


async def test_domain_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Same domain, differing comment -> COMMENT ON DOMAIN with the target's.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE DOMAIN age AS integer",
            "COMMENT ON DOMAIN age IS 'old'",
        ],
        dst=[
            "CREATE DOMAIN age AS integer",
            "COMMENT ON DOMAIN age IS 'new'",
        ],
        diff=['COMMENT ON DOMAIN "public"."age" IS \'new\''],
    )


async def test_domain_base_type_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A domain's base type cannot be altered; a change must raise rather than emit a
    non-converging migration.
    """
    await gen_setup.assert_unsupported(
        src=["CREATE DOMAIN age AS integer"],
        dst=["CREATE DOMAIN age AS bigint"],
        match="Domain base type change is not supported",
    )
