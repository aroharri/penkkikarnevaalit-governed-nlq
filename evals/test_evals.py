"""
The reconciliation set as a test, so it runs on every change rather than when
somebody remembers to look.

Never calls the API. The rule router is deterministic by construction; model
routers replay recorded responses from cassettes/<provider>/. Providers are
discovered from what has been recorded, so a second model adds a test case for
free. With nothing recorded, those cases skip with a message rather than
quietly passing -- a suite that is green because it tested nothing is worse
than a red one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from evals.run_evals import QUESTIONS, run_router
from nlq.router_llm import recorded_providers

CASSETTES = Path(__file__).resolve().parent / "cassettes"
CASES = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))


def _results(router: str):
    return run_router(router, CASES, record=False)


@pytest.fixture(scope="module")
def rules_results():
    return _results("rules")


def test_the_question_set_covers_all_three_outcomes():
    """A set with no refusals in it cannot demonstrate refusing."""
    outcomes = {c["expect"]["outcome"] for c in CASES}
    assert outcomes == {"ANSWER", "CLARIFY", "REFUSE"}
    assert len(CASES) >= 15, "too small a set to mean anything"


def test_no_router_raised(rules_results):
    for r in rules_results:
        assert r.error is None, f"{r.case['q']!r} raised {r.error!r}"


def test_rule_router_produces_no_wrong_numbers(rules_results):
    """The headline claim, stated precisely.

    A wrong number is a confident figure answering a question nobody asked --
    either answering where the correct response was a question or a refusal, or
    answering with a different metric than the one asked for.

    Note what this does NOT claim: that the answer is always the one intended.
    The gates cannot see intent. They guarantee the number is a defined metric,
    correctly computed, and fully cited -- and the citation is what lets a
    reader catch the rest. See docs/MISSA-TAMA-HAJOAA.md.
    """
    wrong = [r.case["q"] for r in rules_results if r.wrong_number]
    assert not wrong, f"wrong numbers: {wrong}"


def test_rule_router_hit_rate_does_not_regress(rules_results):
    """A floor, not a target. It exists to catch a change that quietly makes
    routing worse, which is otherwise invisible."""
    hits = sum(r.hit for r in rules_results)
    assert hits >= 18, f"hit rate fell to {hits}/{len(rules_results)}"


@pytest.mark.parametrize("provider", recorded_providers() or ["<none recorded>"])
def test_model_routers_produce_no_wrong_numbers(provider):
    """Same gates, a different brain. Runs once per provider that has
    recordings, so adding a second model adds a case here for free.

    If this ever fails while the rule router passes, the safety was coming from
    the model rather than from the gates -- which would make the repo's central
    claim false, and is exactly what this test exists to detect.
    """
    if provider == "<none recorded>":
        pytest.skip("no recorded responses; run: python evals/run_evals.py --record")
    results = _results(provider)

    # Check this FIRST. wrong_number is False for a case that raised, so a run
    # where every case crashed would otherwise pass while testing nothing --
    # which is exactly what happened when a prompt change invalidated the
    # cassettes and this suite stayed green.
    errors = [(r.case["q"], r.error) for r in results if r.error]
    assert not errors, (
        f"{provider}: {len(errors)}/{len(results)} cases raised. "
        f"Cassettes are probably stale -- re-record. First: {errors[0]}"
    )

    wrong = [r.case["q"] for r in results if r.wrong_number]
    assert not wrong, f"{provider} produced wrong numbers: {wrong}"
