"""
Deterministic router. No API key, no network, identical output every run.

It is honestly worse than the LLM router at picking the right metric -- the
reconciliation table in the README prints both scores side by side and does
not hide the gap. It is here for two reasons:

  1. A fresh clone runs without credentials.
  2. It shares the gates with the LLM router, which makes a claim testable:
     router quality changes the hit rate, not the safety. If the rule router
     produced a wrong number that the LLM router did not, the safety would be
     coming from the model, not from the gates.
"""

from __future__ import annotations

import re
import unicodedata

from nlq.gates import Candidate, Proposal
from semantic.catalog import Catalog

# Questions that deliberately reach past the reporting boundary.
CROSS_SCOPE_PATTERNS = [
    r"\bkaikista\b", r"\bkaikkien\b", r"\bkaikki kayttajat\b", r"\bkaikki nostajat\b",
    r"\byli haaste", r"\bkaikissa haaste", r"\bhaasteiden yli\b", r"\bkoko jarjestelm",
    r"\ball users\b", r"\bacross challenges\b", r"\beveryone\b",
]

# Hand-written cue words per metric. The LLM router needs none of this; it is
# the price of working without one.
CUES: dict[str, list[str]] = {
    "crew_total_1rm_kg": ["yhteistulos", "yhteensa", "yhteenlaskettu", "porukan tulos",
                          "ryhman tulos", "kokonaistulos", "yhteispotti"],
    "crew_goal_kg": ["tavoite on", "mika on tavoite", "haasteen tavoite", "tavoiteluku"],
    "crew_member_target_sum_kg": ["omat tavoitteet", "jasenten tavoitteet",
                                  "tavoitteiden summa", "henkilokohtaiset tavoitteet",
                                  # Shared with crew_goal_kg on purpose. A bare
                                  # "what is the target?" fits both, and the tie
                                  # gate turns that into the question it should be.
                                  "on tavoite",
                                  "tavoitteet ovat yhteensa"],
    "crew_goal_gap_kg": ["puuttuu", "kaukana", "viela tarvitaan", "vajaa", "matkaa",
                         "gap", "erotus tavoitteeseen"],
    "crew_goal_fill_pct": ["prosentti", "prosenttia", "%", "puolivalissa", "tayttoaste",
                           "kuinka pitkalla", "saavutettu"],
    "crew_target_fill_pct": ["omista tavoitteista", "omien tavoitteiden", "tayttynyt",
                             "jasenten tavoitteista"],
    "lifter_current_1rm_kg": ["nykyinen", "nyt nostaa", "ykkosmaksimi", "1rm", "kuinka vahva",
                              "paljonko nostaa"],
    "lifter_target_gap_kg": ["omaan tavoitteeseen", "tavoitteestaan", "henkilokohtainen tavoite"],
    "lifter_sessions_last_n_days": ["treenannut", "treenikerrat", "kuinka aktiivinen",
                                    "montako kertaa", "salilla", "aktiivisuus"],
}

DAYS_PATTERNS = [
    (r"(\d+)\s*paiv", 1),
    (r"(\d+)\s*viikk", 7),
    (r"(\d+)\s*kuukau", 30),
    (r"viime kuukau", None),   # -> 30
    (r"viime viiko", None),    # -> 7
]


def _fold(text: str) -> str:
    """Strip Finnish diacritics and lowercase, so 'päivän' matches 'paiv'."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def route(question: str, catalog: Catalog, warehouse) -> Proposal:
    q = _fold(question)

    crosses = any(re.search(p, q) for p in CROSS_SCOPE_PATTERNS)

    scores: dict[str, float] = {}
    for metric_name, cues in CUES.items():
        if metric_name not in catalog.metrics:
            continue
        hits = sum(1 for cue in cues if _fold(cue) in q)
        if hits:
            # Saturating score: more cue words help, but never reach certainty.
            scores[metric_name] = min(0.55 + 0.2 * hits, 0.95)

    # A named lifter is evidence for lifter-grain metrics and against crew ones.
    lifter_entity = None
    named_lifter = None
    for metric in catalog.metrics.values():
        lifter_entity = catalog.entity(metric, "lifter")
        break
    if lifter_entity:
        for _, label in warehouse.entity_values(
            lifter_entity["table"], lifter_entity["key"], lifter_entity["label_column"]
        ):
            # Match the name stem so Finnish inflections ("Iiriksen") still hit.
            if _fold(label)[:4] in q:
                named_lifter = label
                break

    if named_lifter:
        for name in list(scores):
            if catalog.get(name).grain == "lifter":
                scores[name] += 0.10
            else:
                # A question naming one person is weak evidence for a crew-level
                # number. "How many kilos has Aada lifted in total?" shares the
                # word "total" with the crew metric and means something else
                # entirely. The penalty is large enough to push a single keyword
                # match below the confidence gate, so it asks instead of guessing.
                scores[name] -= 0.25
        # "How is X doing?" with no other cue: every lifter metric is equally
        # plausible, which is exactly what the tie gate exists for.
        if not scores:
            for name, metric in catalog.metrics.items():
                if metric.grain == "lifter":
                    scores[name] = 0.65

    days = _extract_days(q)

    candidates = [
        Candidate(
            metric=name,
            confidence=round(max(0.0, min(score, 0.99)), 2),
            filters={"lifter": named_lifter} if named_lifter and catalog.get(name).grain == "lifter" else {},
            params={"days": days} if days and "days" in catalog.get(name).requires_params else {},
        )
        for name, score in sorted(scores.items(), key=lambda kv: -kv[1])
    ]

    return Proposal(candidates=candidates, crosses_scope=crosses, raw={"router": "rules"})


def _extract_days(q: str) -> int | None:
    for pattern, multiplier in DAYS_PATTERNS:
        m = re.search(pattern, q)
        if not m:
            continue
        if multiplier is None:
            return 30 if "kuukau" in pattern else 7
        return int(m.group(1)) * multiplier
    return None
