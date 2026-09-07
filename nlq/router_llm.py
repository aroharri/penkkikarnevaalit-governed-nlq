"""
LLM router. Proposes a ranked list of metrics; never computes anything.

Three things the prompt deliberately does NOT contain: SQL, table names, and
column names. The model cannot write a query even if it decides to, because it
has never been shown what a query here looks like. It sees metric names, their
plain-language descriptions, and example questions -- the same material a new
colleague would be handed.

Responses are cached to evals/cassettes/ keyed by a hash of the question and
the catalogue. Tests replay from the cache and never reach the network: a test
whose result changes between runs is not a test.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from nlq.gates import Candidate, Proposal
from semantic.catalog import Catalog

MODEL = "claude-sonnet-5"
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


def _cassette_path(question: str, catalog_text: str) -> Path:
    digest = hashlib.sha256(f"{question}\x00{catalog_text}".encode()).hexdigest()[:16]
    return CASSETTE_DIR / f"{digest}.json"


def route(question: str, catalog: Catalog, warehouse, *, record: bool = False,
          offline: bool = False) -> Proposal:
    catalog_text = catalog_prompt(catalog)
    cassette = _cassette_path(question, catalog_text)

    if cassette.exists() and not record:
        payload = json.loads(cassette.read_text(encoding="utf-8"))["response"]
    elif offline:
        raise LookupError(
            f"No recorded response for: {question!r}\n"
            f"Run with --record and an ANTHROPIC_API_KEY to record it."
        )
    else:
        payload = _call_api(question, catalog_text)
        CASSETTE_DIR.mkdir(parents=True, exist_ok=True)
        cassette.write_text(
            json.dumps({"question": question, "model": MODEL, "response": payload}, indent=2),
            encoding="utf-8",
        )

    return _to_proposal(payload)


def _call_api(question: str, catalog_text: str) -> dict:
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Catalogue:\n{catalog_text}\n\nQuestion: {question}\n\nJSON only.",
        }],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
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
