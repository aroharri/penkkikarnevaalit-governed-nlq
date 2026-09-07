"""
Repo-wide test guard: no test may reach the network.

The README promises that tests never call an API. Until this file existed that
was an intention, not a fact -- and it was already false. tests/test_cli_show.py
calls cli.main(), main() calls load_dotenv(), and load_dotenv writes .env into
os.environ for the whole pytest process. A later test then asked a model router
a question it had no recording for, and the router did the obvious thing: it
called the API and spent money.

Nothing was broken by that. It just quietly stopped being true, which is how a
promise in a README differs from a lock in the code -- the same distinction this
repo makes about metrics, applied to itself.

Applies to tests/ and evals/ alike, which is why it sits at the root.
"""

from __future__ import annotations

import pytest

from nlq import providers

_KEY_ENVS = sorted({p.key_env for p in providers.PROVIDERS.values()})


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    """Remove every provider credential for the duration of each test.

    A router without a key cannot call anything, so a missing recording fails
    loudly instead of silently becoming a paid request. Opt out with
    @pytest.mark.allow_network for a test that deliberately records.
    """
    if request.node.get_closest_marker("allow_network"):
        return
    for key_env in _KEY_ENVS:
        monkeypatch.delenv(key_env, raising=False)
    # LLM_PROVIDER too: it names a provider without proving a key exists, so
    # leaving it set makes selected() hand back something uncallable.
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "allow_network: test may use a real provider key (none do today)"
    )
