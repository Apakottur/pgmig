from pgmig._diff._core import RenameDiff
from pgmig._diff.constraints import _diff_constraints
from pgmig._models import Constraint


def _fk(name: str, definition: str) -> Constraint:
    return Constraint(
        name=name, definition=definition, contype="f", columns=[], comment=None, deferrable=False, deferred=False
    )


def _check(name: str, definition: str) -> Constraint:
    return Constraint(
        name=name, definition=definition, contype="c", columns=[], comment=None, deferrable=False, deferred=False
    )


def _diff(src: dict[str, Constraint], dst: dict[str, Constraint]) -> tuple[RenameDiff, list[str], list[str]]:
    return _diff_constraints(schema_name="public", table_name="t", src=src, dst=dst)


def test_fk_enforce_to_not_enforced_becomes_alter() -> None:
    # Only the enforced state differs -> a single ALTER CONSTRAINT ... NOT ENFORCED, no recreate.
    src = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id)")}
    dst = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id) NOT ENFORCED")}
    diff, alters, validations = _diff(src, dst)
    assert alters == ['ALTER TABLE "public"."t" ALTER CONSTRAINT "c" NOT ENFORCED;']
    assert validations == []
    assert diff.drops == []
    assert diff.creates == []
    assert diff.recreated == set()


def test_fk_not_enforced_to_enforced_becomes_alter() -> None:
    # The reverse direction emits ALTER CONSTRAINT ... ENFORCED.
    src = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id) NOT ENFORCED")}
    dst = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id)")}
    diff, alters, validations = _diff(src, dst)
    assert alters == ['ALTER TABLE "public"."t" ALTER CONSTRAINT "c" ENFORCED;']
    assert validations == []
    assert diff.drops == []
    assert diff.creates == []


def test_fk_definition_change_still_recreates() -> None:
    # A real definition change (not just enforcement) is a drop + re-add, not an alter.
    src = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id)")}
    dst = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id) ON DELETE CASCADE")}
    diff, alters, validations = _diff(src, dst)
    assert alters == []
    assert validations == []
    assert diff.drops == ['ALTER TABLE "public"."t" DROP CONSTRAINT "c";']
    assert diff.creates == [
        'ALTER TABLE "public"."t" ADD CONSTRAINT "c" FOREIGN KEY (a) REFERENCES p(id) ON DELETE CASCADE;'
    ]


def test_fk_combined_enforcement_and_definition_change_recreates() -> None:
    # When both the definition and the enforced state differ, the canonical forms differ too,
    # so it is a full recreate carrying the new NOT ENFORCED suffix -- not an alter.
    src = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id)")}
    dst = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id) ON DELETE CASCADE NOT ENFORCED")}
    diff, alters, validations = _diff(src, dst)
    assert alters == []
    assert validations == []
    assert diff.creates == [
        'ALTER TABLE "public"."t" ADD CONSTRAINT "c" FOREIGN KEY (a) REFERENCES p(id) ON DELETE CASCADE NOT ENFORCED;'
    ]


def test_fk_enforcement_unchanged_is_noop() -> None:
    # Same definition (both NOT ENFORCED) -> nothing to do.
    src = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id) NOT ENFORCED")}
    dst = {"c": _fk("c", "FOREIGN KEY (a) REFERENCES p(id) NOT ENFORCED")}
    diff, alters, validations = _diff(src, dst)
    assert alters == []
    assert validations == []
    assert diff.drops == []
    assert diff.creates == []


def test_check_enforcement_change_recreates() -> None:
    # Postgres rejects altering a check constraint's enforceability in place, so the enforced-state
    # change is a drop + re-add: the enforcement extractor is gated on foreign keys and skips it.
    src = {"c": _check("c", "CHECK ((a > 0))")}
    dst = {"c": _check("c", "CHECK ((a > 0)) NOT ENFORCED")}
    diff, alters, validations = _diff(src, dst)
    assert alters == []
    assert validations == []
    assert diff.drops == ['ALTER TABLE "public"."t" DROP CONSTRAINT "c";']
    assert diff.creates == ['ALTER TABLE "public"."t" ADD CONSTRAINT "c" CHECK ((a > 0)) NOT ENFORCED;']
