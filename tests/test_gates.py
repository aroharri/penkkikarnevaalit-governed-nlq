"""
The gates, driven directly with hand-built proposals.

Routers are tested separately. These tests bypass them on purpose, because the
gates are what the safety claim rests on: whatever a router proposes, however
confidently, these decisions are the same.
"""

from __future__ import annotations

from nlq.gates import Candidate, Outcome, Proposal, decide


def _decide(warehouse, catalog, candidates, crosses_scope=False):
    return decide(Proposal(candidates=candidates, crosses_scope=crosses_scope), catalog, warehouse)


def test_no_candidates_refuses(frozen, catalog):
    d = _decide(frozen, catalog, [])
    assert d.outcome is Outcome.REFUSE
    assert d.reason == "no_metric"
    assert d.alternatives == catalog.metric_names()


def test_an_invented_metric_name_is_dropped_not_looked_up_leniently(frozen, catalog):
    """A model naming a metric that does not exist gets nothing, not the
    closest match. Fuzzy resolution here would defeat the closed list."""
    d = _decide(frozen, catalog, [Candidate("crew_total_1rm_kilos", 0.99)])
    assert d.outcome is Outcome.REFUSE
    assert d.reason == "no_metric"


def test_a_weak_top_candidate_asks_rather_than_guesses(frozen, catalog):
    d = _decide(frozen, catalog, [Candidate("crew_total_1rm_kg", 0.4)])
    assert d.outcome is Outcome.CLARIFY
    assert d.reason == "weak_match"


def test_a_near_tie_asks_rather_than_picking_a_side(frozen, catalog):
    """The gate that matters most: a closed list stops invented SQL, but only
    this stops a confident pick between two equally plausible readings."""
    d = _decide(frozen, catalog, [
        Candidate("crew_total_1rm_kg", 0.74),
        Candidate("crew_goal_gap_kg", 0.71),
    ])
    assert d.outcome is Outcome.CLARIFY
    assert d.reason == "ambiguous"
    assert set(d.alternatives) >= {"crew_total_1rm_kg", "crew_goal_gap_kg"}


def test_a_clear_winner_is_allowed_through(frozen, catalog):
    d = _decide(frozen, catalog, [
        Candidate("crew_total_1rm_kg", 0.92),
        Candidate("crew_goal_gap_kg", 0.40),
    ])
    assert d.outcome is Outcome.ANSWER


def test_an_undeclared_filter_is_refused(frozen, catalog):
    d = _decide(frozen, catalog, [Candidate("crew_total_1rm_kg", 0.9, filters={"gym": "X"})])
    assert d.outcome is Outcome.REFUSE
    assert d.reason == "unknown_filter"


def test_a_name_that_is_not_in_the_data_is_refused_not_zeroed(frozen, catalog):
    """The worst available answer here is 0 kg, because it looks like a number.
    An empty result is just as bad. Both are refused instead."""
    d = _decide(frozen, catalog, [
        Candidate("lifter_target_gap_kg", 0.95, filters={"lifter": "Matti"}),
    ])
    assert d.outcome is Outcome.REFUSE
    assert d.reason == "unknown_value"
    assert "Aada" in d.message and "Bertta" in d.message


def test_name_matching_is_case_insensitive_but_not_fuzzy(frozen, catalog):
    ok = _decide(frozen, catalog, [
        Candidate("lifter_target_gap_kg", 0.95, filters={"lifter": "aaDA"}),
    ])
    assert ok.outcome is Outcome.ANSWER
    assert ok.filters["lifter"] == "Aada"

    near_miss = _decide(frozen, catalog, [
        Candidate("lifter_target_gap_kg", 0.95, filters={"lifter": "Aadaa"}),
    ])
    assert near_miss.outcome is Outcome.REFUSE, (
        "A near miss must fail loudly. Resolving it quietly would answer about "
        "the wrong person with full confidence."
    )


def test_a_missing_required_window_is_asked_for_not_assumed(frozen, catalog):
    d = _decide(frozen, catalog, [Candidate("lifter_sessions_last_n_days", 0.95)])
    assert d.outcome is Outcome.CLARIFY
    assert d.reason == "missing_param"


def test_a_question_across_the_boundary_is_refused(frozen, catalog):
    d = _decide(frozen, catalog, [Candidate("crew_total_1rm_kg", 0.9)], crosses_scope=True)
    assert d.outcome is Outcome.REFUSE
    assert d.reason == "scope_violation"


def test_a_single_challenge_is_resolved_and_flagged_as_inferred(frozen, catalog):
    d = _decide(frozen, catalog, [Candidate("crew_total_1rm_kg", 0.9)])
    assert d.outcome is Outcome.ANSWER
    assert d.scope_value == "X1"
    assert d.scope_was_inferred is True, (
        "Inferring the scope is fine. Not saying so is not: the reader cannot "
        "judge a number without knowing what it covers."
    )


def test_two_challenges_cannot_be_inferred_so_the_gate_asks(frozen_multi, catalog):
    """Same code, more data. Nothing special-cased: the moment a second
    challenge exists, the question starts being asked."""
    d = _decide(frozen_multi, catalog, [Candidate("crew_total_1rm_kg", 0.9)])
    assert d.outcome is Outcome.CLARIFY
    assert d.reason == "scope_ambiguous"
    assert set(d.alternatives) == {"Testihaaste A", "Testihaaste B"}


def test_naming_a_challenge_that_does_not_exist_is_refused(frozen_multi, catalog):
    d = _decide(frozen_multi, catalog, [
        Candidate("crew_total_1rm_kg", 0.9, filters={"challenge": "Talvihaaste"}),
    ])
    assert d.outcome is Outcome.REFUSE
    assert d.reason == "unknown_scope"
