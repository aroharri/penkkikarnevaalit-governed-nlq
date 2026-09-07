"""
LLM router. Proposes a ranked list of metrics; never computes anything.

Three things the prompt deliberately does NOT contain: SQL, table names, and
column names. The model cannot write a query even if it decides to, because it
has never been shown what a query here looks like. It sees metric names, their
plain-language descriptions, and example questions -- the same material a new
colleague would be handed.

Which model answers is a setting, not a design decision: see nlq/providers.py.
Anthropic, xAI, Groq, Google, OpenRouter and a local Ollama all reach the same
gates through the same parsing. That is deliberate. The repo claims the model
is the thinnest, most replaceable part of an agent, and the reconciliation
table is what turns that claim into evidence -- routers differ in how often
they pick the right metric, and the WRONG NUMBER column stays where it is.

Responses are cached to evals/cassettes/<provider>/, keyed by question,
catalogue, provider and model. Tests replay from the cache and never reach the
network: a test whose result changes between runs is not a test.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from nlq import providers
from nlq.gates import Candidate, Proposal
from nlq.providers import Provider
from semantic.catalog import Catalog

CASSETTE_DIR = Path(__file__).resolve().parent.parent / "evals" / "cassettes"

SYSTEM = """You route questions to metrics in a locked catalogue. You never
compute numbers and you never write SQL -- a separate deterministic component
does that from the metric definition.

Return ONLY a JSON object:

{
  "candidates": [
    {"metric": "<exact name from the catalogue>",
     "confidence": <0.0-1.0>,
     "filters": {"lifter": "<name>", "challenge": "<name>"},
     "params": {"days": <int>},
     "group_by": ["<dimension>"]}
  ],
  "crosses_scope": <true|false>
}

Rules:
- Only use metric names that appear in the catalogue. Never invent one.
- Rank every metric that plausibly fits, with honest confidences. If two
  readings are equally plausible, give them similar confidences: a downstream
  gate turns near-ties into a clarifying question, which is the correct
  outcome. Do not break a tie to seem decisive.
- If nothing fits, return an empty candidates list. Refusing is a valid answer.
- Set crosses_scope to true when the question deliberately asks across all
  challenges or all users rather than within one challenge.
- Only include filters, params and group_by that the metric declares.
- Omit params you were not given. Do not invent a time window."""


def catalog_prompt(catalog: Catalog) -> str:
    """Everything the model is allowed to see. No SQL, no schema."""
    lines = []
    for name in catalog.metric_names():
        m = catalog.get(name)
        lines.append(f"- {name}")
        lines.append(f"    label: {m.label}")
        lines.append(f"    grain: {m.grain}   unit: {m.unit}")
        if m.note:
            note = " ".join(m.note.split())
            lines.append(f"    note: {note}")
        if m.filterable_dimensions:
            lines.append(f"    filters: {', '.join(m.filterable_dimensions)}")
        if m.allowed_dimensions:
            lines.append(f"    group_by: {', '.join(m.allowed_dimensions)}")
        if m.requires_params:
            lines.append(f"    requires: {', '.join(m.requires_params)}")
        for ex in m.examples:
            lines.append(f"    example: {ex}")
    return "\n".join(lines)


def _cassette_path(question: str, catalog_text: str, provider: Provider) -> Path:
    """One recording per (question, catalogue, provider, model).

    The model belongs in the key. Without it, recording with one provider and
    then running another replays the first one's answers and reports them as
    the second one's score -- two rows of the same data under different names.
    A reconciliation table that quietly compares a thing with itself is exactly
    the kind of plausible-looking wrong number this repo exists to prevent.
    """
    key = f"{question}\x00{catalog_text}\x00{provider.name}\x00{provider.model}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return CASSETTE_DIR / provider.name / f"{digest}.json"


def recorded_providers() -> list[str]:
    """Providers that have recordings, so the evals can run them offline."""
    if not CASSETTE_DIR.exists():
        return []
    return sorted(d.name for d in CASSETTE_DIR.iterdir()
                  if d.is_dir() and any(d.glob("*.json")))


def route(question: str, catalog: Catalog, warehouse, *, record: bool = False,
          offline: bool = False, provider: str | None = None) -> Proposal:
    prov = providers.get(provider) if provider else providers.selected()
    catalog_text = catalog_prompt(catalog)
    cassette = _cassette_path(question, catalog_text, prov)

    if cassette.exists() and not record:
        payload = json.loads(cassette.read_text(encoding="utf-8"))["response"]
    elif offline:
        raise LookupError(
            f"No recorded response from {prov.name} for: {question!r}\n"
            f"Record it with:  LLM_PROVIDER={prov.name} {prov.key_env}=... "
            f"python evals/run_evals.py --record"
        )
    else:
        payload = _call_api(question, catalog_text, prov)
        cassette.parent.mkdir(parents=True, exist_ok=True)
        cassette.write_text(
            json.dumps({"question": question, "provider": prov.name, "model": prov.model,
                        "response": payload}, indent=2),
            encoding="utf-8",
        )

    return _to_proposal(payload)


def _user_prompt(question: str, catalog_text: str) -> str:
    return f"Catalogue:\n{catalog_text}\n\nQuestion: {question}\n\nJSON only."


def _call_api(question: str, catalog_text: str, prov: Provider) -> dict:
    """Dispatch on wire protocol. The prompt, the parsing and every gate
    downstream are identical -- only the transport differs."""
    if not prov.has_key:
        raise RuntimeError(f"{prov.key_env} is not set (provider: {prov.name}).")
    if prov.protocol == "anthropic":
        text = _call_anthropic(question, catalog_text, prov)
    else:
        text = _call_openai_compatible(question, catalog_text, prov)
    return _parse_json(text)


def _call_anthropic(question: str, catalog_text: str, prov: Provider) -> str:
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=prov.model,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": _user_prompt(question, catalog_text)}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def _call_openai_compatible(question: str, catalog_text: str, prov: Provider) -> str:
    """One code path for xAI, Groq, Google, OpenRouter, Cerebras and Ollama.

    Uses urllib rather than a vendor SDK: the request is one POST of plain
    JSON, and depending on a client library per provider would put more code in
    the layer this module is trying to keep thin.
    """
    import urllib.error
    import urllib.request

    body = json.dumps({
        "model": prov.model,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _user_prompt(question, catalog_text)},
        ],
    }).encode()

    request = urllib.request.Request(
        prov.base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ[prov.key_env]}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{prov.name} returned {exc.code}: {exc.read()[:300]!r}") from exc
    return payload["choices"][0]["message"]["content"].strip()


def _parse_json(text: str) -> dict:
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    return json.loads(text)


def _to_proposal(payload: dict) -> Proposal:
    """Validate the model's output against the expected shape.

    Anything malformed becomes zero candidates, which the gates turn into a
    refusal. A router that returns nonsense must fail closed.
    """
    candidates = []
    for raw in payload.get("candidates") or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("metric"), str):
            continue
        try:
            confidence = float(raw.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        filters = raw.get("filters") or {}
        params = raw.get("params") or {}
        group_by = raw.get("group_by") or []
        if not isinstance(filters, dict) or not isinstance(params, dict) or not isinstance(group_by, list):
            continue
        candidates.append(Candidate(
            metric=raw["metric"],
            confidence=max(0.0, min(confidence, 1.0)),
            filters={str(k): str(v) for k, v in filters.items() if v not in (None, "")},
            params=params,
            group_by=[str(g) for g in group_by],
        ))

    return Proposal(
        candidates=candidates,
        crosses_scope=bool(payload.get("crosses_scope")),
        raw={"router": "llm", **payload},
    )
