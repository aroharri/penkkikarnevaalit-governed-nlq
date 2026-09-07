"""
The keyword router. It is meant to be worse than a model at choosing, not
worse at being careful.

The interesting tests are the ones about names, because that is where a
matcher invents facts: the gates can refuse a name that is not in the data, but
nothing downstream can notice a name the question never contained.
"""

from __future__ import annotations

import pytest

from nlq import router_rules


def named(question, catalog, warehouse):
    """Which lifter, if any, this question is read as being about."""
    proposal = router_rules.route(question, catalog, warehouse)
    for candidate in proposal.candidates:
        if "lifter" in candidate.filters:
            return candidate.filters["lifter"]
    return None


@pytest.mark.parametrize("question,expected", [
    ("Miten Aadalla menee?", "Aada"),
    ("Paljonko Aadalta puuttuu omaan tavoitteeseen?", "Aada"),
    ("Mika on Bertan nykyinen ykkosmaksimi?", "Bertta"),
])
def test_finnish_inflections_still_resolve(question, expected, catalog, frozen):
    """Names arrive inflected -- "Bertan", "Aadalta" -- so matching the stem is
    the point. Requiring an exact nominative would refuse ordinary questions."""
    assert named(question, catalog, frozen) == expected


@pytest.mark.parametrize("question", [
    "Miten Pekalla menee?",
    "Paljonko Pekalla on?",
])
def test_a_name_that_merely_contains_a_stem_is_not_a_match(question, catalog, frozen):
    """Regression. The stem test was a bare substring, so "pe-KALL-a" read as
    Kalle and the router filtered on a person the question never mentioned.

    The gates cannot catch this. They check that a named person exists, and
    Kalle does exist -- what they cannot see is that nobody named him. A
    fabricated filter is worse than an unknown one: the unknown one is refused,
    this one would have been answered.
    """
    assert named(question, catalog, frozen) is None


def test_an_unknown_person_produces_no_lifter_filter(catalog, frozen):
    assert named("Miten Matilla menee?", catalog, frozen) is None


def test_naming_someone_argues_against_crew_level_metrics(catalog, frozen):
    """"How many kilos has Aada lifted in total?" shares the word "total" with
    the crew metric and means something else entirely. One keyword is not
    enough evidence to answer it as a crew number."""
    proposal = router_rules.route(
        "Montako kiloa Aada on nostanut yhteensa kaikissa treeneissa?", catalog, frozen)
    crew = [c for c in proposal.candidates
            if catalog.get(c.metric).grain == "challenge" and c.confidence >= 0.60]
    assert not crew, f"a crew metric passed the confidence gate: {crew}"


def test_a_question_across_the_boundary_is_flagged(catalog, frozen):
    proposal = router_rules.route("Kuka on vahvin kaikista kayttajista?", catalog, frozen)
    assert proposal.crosses_scope is True


def test_a_time_window_is_read_from_the_question(catalog, frozen):
    proposal = router_rules.route(
        "Montako kertaa Bertta on treenannut viimeisen 30 paivan aikana?", catalog, frozen)
    days = [c.params.get("days") for c in proposal.candidates if c.params]
    assert 30 in days


def test_no_window_means_no_invented_window(catalog, frozen):
    """A missing window must reach the gate as missing, so the gate can ask.
    Filling in a default here would answer a question nobody asked."""
    proposal = router_rules.route("Kuinka aktiivinen Bertta on ollut?", catalog, frozen)
    assert all("days" not in c.params for c in proposal.candidates)
