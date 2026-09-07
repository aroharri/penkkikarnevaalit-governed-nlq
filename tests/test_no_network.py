"""
The guard that keeps "tests never call an API" true.

A promise in a README is not a mechanism. This one was already false: a test
that called cli.main() pulled .env into os.environ through load_dotenv, and a
later test then asked a model router something it had no recording for. The
router did the obvious thing and paid for an answer.

The root conftest.py now strips every provider credential per test. These
assertions are what notices if that stops working.
"""

from __future__ import annotations

import os

import pytest

from nlq import providers, router_llm
from nlq.gates import Outcome


def test_no_provider_credential_is_visible_during_a_test():
    for provider in providers.PROVIDERS.values():
        assert not os.environ.get(provider.key_env), (
            f"{provider.key_env} is set during a test. Something loaded .env into "
            f"the process, and an unrecorded question would become a paid request."
        )


def test_selecting_a_provider_fails_rather_than_defaulting():
    with pytest.raises(RuntimeError):
        providers.selected()


def test_an_unrecorded_question_cannot_become_a_network_call(catalog, frozen):
    """Offline, a missing recording is a LookupError naming how to record it --
    never a request."""
    with pytest.raises(LookupError) as exc:
        router_llm.route("kysymys jota ei ole koskaan nauhoitettu", catalog, frozen,
                         offline=True, provider="anthropic")
    assert "--record" in str(exc.value)


def test_without_a_key_the_default_router_is_the_offline_one(frozen, catalog):
    from nlq import ask as ask_mod

    assert ask_mod.default_router() == "rules"

    result, _, _ = ask_mod.answer_question(
        "Paljonko porukan yhteistulos on nyt?", catalog, frozen, router="rules")
    assert result.outcome is Outcome.ANSWER
