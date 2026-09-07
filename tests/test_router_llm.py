"""
The model-facing layer: recording, replay, and what happens when a model
returns nonsense.

No network. The API call is stubbed, which is the point -- this tests the
transport and the parsing, and those are the parts that must not need a key to
verify.
"""

from __future__ import annotations

import json

import pytest

from nlq import providers, router_llm
from nlq.gates import Outcome, decide

PAYLOAD = {
    "candidates": [{"metric": "crew_total_1rm_kg", "confidence": 0.93, "filters": {}}],
    "crosses_scope": False,
}


@pytest.fixture
def cassettes(tmp_path, monkeypatch):
    monkeypatch.setattr(router_llm, "CASSETTE_DIR", tmp_path)
    return tmp_path


def test_the_cassette_key_separates_providers_and_models(catalog, cassettes):
    """The bug this guards against is silent and plausible: record with one
    provider, run another, and the second replays the first one's answers under
    its own name. A reconciliation table would then compare a thing with itself
    and look entirely healthy."""
    text = router_llm.catalog_prompt(catalog)
    a = router_llm._cassette_path("Sama kysymys", text, providers.get("anthropic"))
    b = router_llm._cassette_path("Sama kysymys", text, providers.get("groq"))
    assert a != b
    assert a.parent.name == "anthropic" and b.parent.name == "groq"

    same_provider_other_model = providers.Provider(
        name="groq", protocol="openai", model="a-different-model", key_env="GROQ_API_KEY"
    )
    c = router_llm._cassette_path("Sama kysymys", text, same_provider_other_model)
    assert c != b, "changing the model must change the key, not just the provider"


def test_record_then_replay_without_the_network(catalog, frozen, cassettes, monkeypatch):
    calls = []

    def fake_call(question, catalog_text, prov):
        calls.append(prov.name)
        return PAYLOAD

    monkeypatch.setattr(router_llm, "_call_api", fake_call)

    first = router_llm.route("Paljonko porukan yhteistulos on nyt?", catalog, frozen,
                             record=True, provider="groq")
    assert calls == ["groq"]
    assert first.candidates[0].metric == "crew_total_1rm_kg"

    # Second time it must come off disk, not from the (stubbed) API.
    replay = router_llm.route("Paljonko porukan yhteistulos on nyt?", catalog, frozen,
                              provider="groq")
    assert calls == ["groq"], "replay must not call the API again"
    assert replay.candidates[0].metric == "crew_total_1rm_kg"

    assert router_llm.recorded_providers() == ["groq"]

    stored = json.loads(next(cassettes.rglob("*.json")).read_text(encoding="utf-8"))
    assert stored["provider"] == "groq"
    assert stored["model"] == providers.get("groq").model


def test_offline_with_no_recording_says_how_to_record(catalog, frozen, cassettes):
    with pytest.raises(LookupError) as exc:
        router_llm.route("Ei tallennetta talle", catalog, frozen,
                         offline=True, provider="gemini")
    assert "--record" in str(exc.value)
    assert "GEMINI_API_KEY" in str(exc.value)


@pytest.mark.parametrize("payload", [
    {},
    {"candidates": None},
    {"candidates": "not a list"},
    {"candidates": [{"metric": 42, "confidence": 0.9}]},
    {"candidates": [{"confidence": 0.9}]},
    {"candidates": [{"metric": "crew_total_1rm_kg", "confidence": "very sure"}]},
    {"candidates": [{"metric": "crew_total_1rm_kg", "confidence": 0.9, "filters": "Aada"}]},
])
def test_malformed_model_output_fails_closed(payload, catalog, frozen):
    """A model that returns nonsense must produce no candidates, which the
    gates turn into a refusal.

    Failing open here would be the worst possible default: a garbled response
    resolving to whatever metric happened to parse, answered with confidence.
    """
    proposal = router_llm._to_proposal(payload)
    assert proposal.candidates == []
    assert decide(proposal, catalog, frozen).outcome is Outcome.REFUSE


def test_confidence_outside_the_range_is_clamped_not_trusted(catalog):
    proposal = router_llm._to_proposal(
        {"candidates": [{"metric": "crew_total_1rm_kg", "confidence": 7.5}]}
    )
    assert proposal.candidates[0].confidence == 1.0


def test_the_prompt_never_shows_the_model_the_schema(catalog):
    """The model cannot write a query it has never been shown.

    The prompt carries metric names, plain-language descriptions and example
    questions -- the material a new colleague would be handed. It carries no
    table names and no base SQL.

    Checked against the catalogue's own tables and base relations rather than a
    hand-written word list: a new table added later is covered automatically,
    and English prose is not mistaken for SQL. ("falls back from one to the
    other" is not a FROM clause.)

    Dimension keys such as one_rm_source do appear, and are meant to: they are
    the catalogue's vocabulary for what may be grouped by. That one of them
    happens to share a name with a column does not hand the model a schema.
    """
    prompt = (router_llm.catalog_prompt(catalog) + router_llm.SYSTEM).lower()

    dataset = catalog.datasets["lifting"]
    tables = {e["table"].lower() for e in dataset["entities"].values()}
    tables |= {"bridge_memberships", "fct_lifts", "fct_latest_lift"}
    for table in tables:
        assert table not in prompt, f"the prompt leaks the table name {table!r}"

    for base in dataset["bases"].values():
        for line in base["sql"].lower().splitlines():
            if line.strip().startswith(("from ", "join ", "left join ")):
                assert line.strip() not in prompt, f"the prompt leaks base SQL: {line.strip()!r}"
