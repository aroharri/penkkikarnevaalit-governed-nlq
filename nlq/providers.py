"""
Which model answers, and how to reach it.

The router's job is to hand over a prompt and get back JSON. Everything that
differs between vendors lives here, so `router_llm.py` is the same code no
matter who is answering. That is the point rather than a convenience: the repo
claims the model is the thinnest, most replaceable part of an agent, and a
claim like that should be demonstrable, not asserted.

Two wire protocols cover every provider worth having. Anthropic has its own;
xAI, Groq, Google (via its compatibility endpoint), OpenRouter, Cerebras,
Mistral and a local Ollama all speak the OpenAI chat-completions shape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    protocol: str  # "anthropic" | "openai"
    model: str
    key_env: str
    base_url: str | None = None
    note: str = ""

    @property
    def has_key(self) -> bool:
        return bool(os.environ.get(self.key_env))


# Default models are the small, fast ones. Routing is a classification task,
# not a reasoning one, and a weaker model is the more interesting test: if the
# hit rate falls but WRONG NUMBER stays at zero, the safety is coming from the
# gates rather than from the model. That is the whole argument.
PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider(
        name="anthropic",
        protocol="anthropic",
        model=os.environ.get("LLM_MODEL_ANTHROPIC", "claude-sonnet-5"),
        key_env="ANTHROPIC_API_KEY",
    ),
    "gemini": Provider(
        name="gemini",
        protocol="openai",
        model=os.environ.get("LLM_MODEL_GEMINI", "gemini-3.6-flash"),
        key_env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        note="Google AI Studio has a standing free tier and needs no card.",
    ),
    "groq": Provider(
        name="groq",
        protocol="openai",
        model=os.environ.get("LLM_MODEL_GROQ", "openai/gpt-oss-120b"),
        key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        note="Groq the inference company, not Grok the model. Free tier.",
    ),
    "xai": Provider(
        name="xai",
        protocol="openai",
        model=os.environ.get("LLM_MODEL_XAI", "grok-4"),
        key_env="XAI_API_KEY",
        base_url="https://api.x.ai/v1",
        note="Grok. No standing free tier; sign-up credit only.",
    ),
    "openrouter": Provider(
        name="openrouter",
        protocol="openai",
        model=os.environ.get("LLM_MODEL_OPENROUTER", "meta-llama/llama-3.3-70b-instruct"),
        key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
    ),
    "ollama": Provider(
        name="ollama",
        protocol="openai",
        model=os.environ.get("LLM_MODEL_OLLAMA", "llama3.1"),
        key_env="OLLAMA_HOST",
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/v1",
        note="Local. No key and no network; set OLLAMA_HOST to enable.",
    ),
}


def get(name: str) -> Provider:
    if name not in PROVIDERS:
        raise KeyError(f"Unknown provider {name!r}. Known: {', '.join(PROVIDERS)}")
    return PROVIDERS[name]


def selected() -> Provider:
    """The provider to call when recording.

    LLM_PROVIDER wins. Otherwise the first one holding a key, so a clone with a
    single key configured just works.
    """
    if name := os.environ.get("LLM_PROVIDER"):
        return get(name)
    for provider in PROVIDERS.values():
        if provider.has_key:
            return provider
    raise RuntimeError(
        "No LLM provider configured. Set one of: "
        + ", ".join(p.key_env for p in PROVIDERS.values())
        + "\nOr use the rule router, which needs no key: --router rules"
    )
