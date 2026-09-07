"""
The arithmetic, against the frozen fixture.

Every expected number below is computed by hand from tests/fixtures/data/.
Brzycki at 5 reps is exactly 36/32 = 1.125, so the fixture's weights were
chosen to produce whole numbers a reader can verify without a calculator.

Fixture, in full:

    Aada  (F1, member of X1, personal target 120)
        2026-01-10   100 kg x 1  -> 100.0   real max
        2026-03-01    80 kg x 5  ->  90.0   Brzycki estimate   <- latest
    Bertta (F2, member of X1, personal target 130)
        2026-02-01    96 kg x 5  -> 108.0   Brzycki estimate
        2026-04-01   110 kg x 1  -> 110.0   real max           <- latest
        2026-05-01   200 kg x 13 -> EXCLUDED, outside 1-12 reps
    Daavid (F3, member of NO challenge)
        2026-02-20   150 kg x 1  -> 150.0   must never reach a metric

    Challenge X1 goal: 300 kg
"""

from __future__ import annotations

import pytest

from tests.conftest import AS_OF, value

CREW_TOTAL = 200.0        # 90.0 (Aada latest) + 110.0 (Bertta latest)
MEMBER_TARGETS = 250.0    # 120 + 130
CHALLENGE_GOAL = 300.0


def test_brzycki_at_one_rep_is_the_weight_itself(frozen):
    """At reps = 1 the factor is 36/(37-1) = 1.0 exactly.

    So a single is not "an estimate that happens to be accurate": it is the
    weight that was lifted. That distinction is the whole of
    docs/oikea-vs-laskennallinen.md, and it holds arithmetically or not at all.
    """
    rows = frozen.run("select weight_kg, one_rm_kg from fct_lifts where reps = 1")
    assert rows, "fixture must contain single-rep sets"
    for weight, one_rm in rows:
        assert one_rm == pytest.approx(weight)


def test_brzycki_at_five_reps(frozen):
    rows = dict(frozen.run("select lift_id, one_rm_kg from fct_lifts where reps = 5"))
    assert rows["L02"] == pytest.approx(90.0)    # 80 * 1.125
    assert rows["L03"] == pytest.approx(108.0)   # 96 * 1.125


def test_sets_outside_the_rep_range_are_excluded(frozen):
    """L06 is 200 kg x 13. Brzycki would call that 300 kg, which would be the
    single largest number in the fixture. It must not be in the warehouse."""
    assert frozen.run("select count(*) from fct_lifts where lift_id = 'L06'")[0][0] == 0


def test_crew_total(frozen, catalog):
    assert value(frozen, catalog, "crew_total_1rm_kg") == pytest.approx(CREW_TOTAL)


def test_crew_goal_and_gap(frozen, catalog):
    assert value(frozen, catalog, "crew_goal_kg") == pytest.approx(CHALLENGE_GOAL)
    assert value(frozen, catalog, "crew_goal_gap_kg") == pytest.approx(100.0)


def test_the_two_competing_denominators_are_kept_apart(frozen, catalog):
    """The challenge's own goal (300) and the sum of members' personal targets
    (250) are different numbers. The app falls back from one to the other; the
    catalogue exposes both under separate names instead."""
    assert value(frozen, catalog, "crew_goal_kg") == pytest.approx(300.0)
    assert value(frozen, catalog, "crew_member_target_sum_kg") == pytest.approx(MEMBER_TARGETS)


def test_ratio_of_sums_is_not_the_average_of_ratios(frozen, catalog):
    """The reason no percentage is stored in a column.

    Per member, against their own target:
        Aada    90 / 120 = 75.000 %
        Bertta 110 / 130 = 84.615 %
        average          = 79.808 %      <- what dragging a formula down gives

    Correctly:
        (90 + 110) / (120 + 130) = 80.000 %

    The average weights Aada's 120 kg target the same as Bertta's 130 kg. Nobody
    means to claim that; it arrives for free with the wrong formula. The gap is
    small here and grows with the spread of the denominators.
    """
    correct = value(frozen, catalog, "crew_target_fill_pct")
    assert correct == pytest.approx(80.0)

    per_member = frozen.run("""
        select f.one_rm_kg / m.target_1rm_kg * 100
        from bridge_memberships m
        join fct_latest_lift f on f.lifter_id = m.lifter_id
        where m.challenge_id = 'X1'
    """)
    average_of_ratios = sum(r[0] for r in per_member) / len(per_member)

    assert average_of_ratios == pytest.approx(79.8076923, abs=1e-6)
    assert average_of_ratios != pytest.approx(correct, abs=0.01), (
        "If these ever match, the fixture has stopped demonstrating the point."
    )


def test_real_and_estimated_are_reported_separately(frozen, catalog):
    """200.0 kg is not one kind of number. Bertta's 110 was lifted; Aada's 90
    was modelled. A total that hides the split is the reporting equivalent of
    an actual that silently contains accruals."""
    sql, args = catalog.compile("crew_total_1rm_kg", scope_value="X1",
                                group_by=["one_rm_source"])
    by_source = {row[0]: row[1] for row in frozen.run(sql, args)}
    assert by_source["true_max"] == pytest.approx(110.0)
    assert by_source["brzycki_estimate"] == pytest.approx(90.0)
    assert sum(by_source.values()) == pytest.approx(CREW_TOTAL)


def test_lifter_grain_returns_one_row_per_member(frozen, catalog):
    sql, args = catalog.compile("lifter_target_gap_kg", scope_value="X1")
    rows = dict(frozen.run(sql, args))
    assert rows == {"Aada": pytest.approx(30.0), "Bertta": pytest.approx(20.0)}


def test_a_member_with_no_sessions_shows_zero_not_absence(frozen, catalog):
    """A window of one day catches nothing. Both members must still appear.

    A name missing from a list reads as "not asked about". A name showing 0
    reads as "asked, and the answer is none". Only one of those is true here,
    and the difference is invisible to the reader unless the row is present.
    """
    sql, args = catalog.compile("lifter_sessions_last_n_days", scope_value="X1",
                                params={"days": 1}, as_of=AS_OF)
    rows = dict(frozen.run(sql, args))
    assert rows == {"Aada": 0, "Bertta": 0}


def test_an_orphans_lift_never_reaches_a_metric(frozen, catalog):
    """Daavid is in the data and has lifted 150 kg, but belongs to no challenge.

    If scoping failed, the crew total would be 350.0 rather than 200.0 -- a
    number that looks entirely reasonable and is wrong by three quarters. The
    equivalent in a ledger is a booking with no cost centre: present, plausible,
    and attributed to whoever happens to be reading.
    """
    daavid = frozen.run("select one_rm_kg from fct_latest_lift where lifter_id = 'F3'")
    assert daavid and daavid[0][0] == pytest.approx(150.0), "the orphan must have a lift"

    assert value(frozen, catalog, "crew_total_1rm_kg") == pytest.approx(CREW_TOTAL)
    assert value(frozen, catalog, "crew_total_1rm_kg") != pytest.approx(CREW_TOTAL + 150.0)

    sql, args = catalog.compile("lifter_current_1rm_kg", scope_value="X1")
    assert "Daavid" not in dict(frozen.run(sql, args))


def test_the_source_split_is_only_shown_where_it_is_a_split(frozen, catalog):
    """At lifter grain the compiled query groups by lifter as well, so
    collapsing those rows by source keeps one arbitrary lifter per source: two
    numbers that sum to nothing in particular, printed under a total they do
    not explain. The answer must not offer a breakdown there.
    """
    from nlq.answer import _source_split
    from nlq.gates import Candidate, Proposal, decide

    crew = decide(Proposal(candidates=[Candidate("crew_total_1rm_kg", 0.9)]), catalog, frozen)
    split = _source_split(crew, catalog, frozen)
    assert split, "a crew total must show what is measured and what is modelled"
    assert sum(v for _, v in split) == pytest.approx(CREW_TOTAL), (
        "a breakdown that does not add up to the number above it is worse than none"
    )

    per_lifter = decide(Proposal(candidates=[Candidate("lifter_current_1rm_kg", 0.9)]),
                        catalog, frozen)
    assert _source_split(per_lifter, catalog, frozen) == []
