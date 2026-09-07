"""
The gates. This is the core of the repo.

A router proposes; the gates decide. Everything in this module is ordinary
deterministic code -- no language model is consulted here, and none of these
decisions can be talked out of.

The reasoning behind that split: a closed list of metrics stops a model
inventing SQL, but it does not stop it confidently picking the WRONG metric.
"How is Reino doing?" matches three metrics equally well, and the correct
response is a question, not the best guess. So the router returns a ranked
list, and a tie becomes a clarification rather than a coin flip.

Gate order matters and is the same for every router, which is why routers
differ in how often they pick the right metric but not in how safe they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from semantic.catalog import Catalog, Metric

# A top candidate below this is a guess, not a match.
WEAK_CONFIDENCE = 0.60
# Two candidates this close cannot be told apart. Asking beats guessing.
TIE_GAP = 0.15


class Outcome(str, Enum):
    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    REFUSE = "REFUSE"


@dataclass
class Candidate:
    metric: str
    confidence: float
    filters: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    group_by: list[str] = field(default_factory=list)


@dataclass
class Proposal:
    """What a router hands over. Note what it is not: an answer."""

    candidates: list[Candidate] = field(default_factory=list)
    crosses_scope: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class Decision:
    outcome: Outcome
    reason: str = ""
    message: str = ""
    metric: Metric | None = None
    scope_entity: str = ""
    scope_value: str = ""
    scope_label: str = ""
    scope_was_inferred: bool = False
    filters: dict[str, str] = field(default_factory=dict)
    group_by: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    alternatives: list[str] = field(default_factory=list)


def _dimension_labels(catalog: Catalog, metric: Metric) -> str:
    """Human labels, not the catalogue's internal keys.

    A reader who asked about a gym does not know that the system calls the
    thing it CAN do "lifter" -- naming the internals in an error tells them
    nothing they can act on.
    """
    dimensions = catalog.datasets[metric.dataset]["dimensions"]
    return ", ".join(dimensions.get(d, {}).get("label", d).lower()
                     for d in metric.filterable_dimensions)


def decide(proposal: Proposal, catalog: Catalog, warehouse, question: str = "") -> Decision:
    """Run every gate in order. The first one that fires wins."""

    known = [c for c in proposal.candidates if c.metric in catalog.metrics]

    # Gate 1 -- nothing matched. Includes the case where a model named a metric
    # that does not exist: it is dropped rather than looked up leniently.
    if not known:
        return Decision(
            Outcome.REFUSE,
            reason="no_metric",
            message="Katalogissa ei ole mittaria, joka vastaisi tahan kysymykseen.",
            alternatives=catalog.metric_names(),
        )

    known.sort(key=lambda c: c.confidence, reverse=True)
    top = known[0]
    metric = catalog.get(top.metric)

    # Gate 2 -- the question deliberately reaches past the reporting boundary.
    # Answering across challenges would put another group's numbers in front of
    # this group's readers. That is a different question, not a wider version of
    # the same one, so it is refused rather than silently widened.
    if proposal.crosses_scope:
        return Decision(
            Outcome.REFUSE,
            reason="scope_violation",
            message=(
                "Luvut lasketaan aina yhden haasteen sisalla, joten en voi "
                "vertailla haasteiden yli."
            ),
        )

    # Gate 3 -- filter keys must be declared on the metric.
    for key in top.filters:
        if key == metric.scope:
            continue
        if key not in metric.filterable_dimensions:
            return Decision(
                Outcome.REFUSE,
                reason="unknown_filter",
                message=(
                    f"en osaa rajata lukua '{key}' mukaan. "
                    + (f"Voin rajata vain naiden mukaan: {_dimension_labels(catalog, metric)}."
                       if metric.filterable_dimensions
                       else f"'{metric.label}' lasketaan koko haasteelle, sita ei voi rajata.")
                ),
            )

    # Gate 4 -- filter values must exist. Exact, case-insensitive, no fuzzy
    # matching: a near miss has to fail loudly. Returning an empty result or a
    # zero here would be the worst answer available, because both look like
    # numbers.
    #
    # This runs BEFORE the confidence gates on purpose. Whether a named person
    # exists is a fact about the data; whether a question is clear is a
    # judgement about the question. Facts first. Asked the other way round,
    # "how is Matti doing?" -- vague AND about nobody -- came back as "please
    # clarify", inviting the reader to rephrase a question that can never be
    # answered.
    resolved_filters: dict[str, str] = {}
    for key, value in top.filters.items():
        if key == metric.scope:
            continue
        if key == "lifter":
            entity = catalog.entity(metric, "lifter")
            known_values = warehouse.entity_values(
                entity["table"], entity["key"], entity["label_column"]
            )
            match = next((lbl for _, lbl in known_values if lbl.lower() == str(value).lower()), None)
            if match is None:
                return Decision(
                    Outcome.REFUSE,
                    reason="unknown_value",
                    message=(
                        f"{value} ei ole datassa.\n\n"
                        f"Nostajat: {', '.join(lbl for _, lbl in known_values)}"
                    ),
                )
            resolved_filters[key] = match
        else:
            dim = catalog.dimension(metric, key)
            allowed = list((dim.get("values") or {}).keys())
            if allowed and str(value) not in allowed:
                return Decision(
                    Outcome.REFUSE,
                    reason="unknown_value",
                    message=f"'{value}' ei ole kelvollinen arvo. Vaihtoehdot: {allowed}",
                )
            resolved_filters[key] = str(value)

    # Gate 5 -- the best match is not good enough to act on.
    if top.confidence < WEAK_CONFIDENCE:
        return Decision(
            Outcome.CLARIFY,
            reason="weak_match",
            message="en tunnistanut kysymysta riittavan varmasti. Tarkoititko jotain naista?",
            alternatives=[c.metric for c in known[:3]],
        )

    # Gate 6 -- two candidates are too close to separate. This is the gate that
    # catches "how is X doing?", where every reading is plausible.
    if len(known) > 1 and (top.confidence - known[1].confidence) < TIE_GAP:
        return Decision(
            Outcome.CLARIFY,
            reason="ambiguous",
            message="kysymys sopii useaan lukuun yhta hyvin, enka arvaa puolestasi.",
            alternatives=[c.metric for c in known[:3]],
        )

    # Gate 7 -- a required parameter with no sensible default. A window is not
    # guessed, because "recently" means different things to different readers.
    missing = [p for p in metric.requires_params if p not in top.params]
    if missing:
        return Decision(
            Outcome.CLARIFY,
            reason="missing_param",
            message=(
                "milta ajalta? Sano esimerkiksi 'viimeisen 30 paivan aikana'."
            ),
            metric=metric,
        )

    # Gate 8 -- scope. Resolvable to exactly one value means resolve it and say
    # so out loud; more than one means ask. Never widen.
    scope_entity = catalog.entity(metric, metric.scope)
    scope_values = warehouse.entity_values(
        scope_entity["table"], scope_entity["key"], scope_entity["label_column"]
    )
    requested = top.filters.get(metric.scope)

    if requested:
        hit = next(
            (kv for kv in scope_values if kv[1].lower() == str(requested).lower()
             or kv[0].lower() == str(requested).lower()),
            None,
        )
        if hit is None:
            return Decision(
                Outcome.REFUSE,
                reason="unknown_scope",
                message=(
                    f"Haastetta {requested} ei ole.\n\n"
                    f"Haasteet: {', '.join(lbl for _, lbl in scope_values)}"
                ),
            )
        scope_key, scope_label, inferred = hit[0], hit[1], False
    elif len(scope_values) == 1:
        scope_key, scope_label, inferred = scope_values[0][0], scope_values[0][1], True
    elif len(scope_values) == 0:
        return Decision(
            Outcome.REFUSE,
            reason="no_scope_values",
            message="datassa ei ole yhtaan haastetta, joten lukuja ei ole mista laskea.",
        )
    else:
        return Decision(
            Outcome.CLARIFY,
            reason="scope_ambiguous",
            message=(
                "mista haasteesta? Luvut lasketaan yhden haasteen sisalla."
            ),
            metric=metric,
            alternatives=[lbl for _, lbl in scope_values],
        )

    return Decision(
        Outcome.ANSWER,
        reason="ok",
        metric=metric,
        scope_entity=metric.scope,
        scope_value=scope_key,
        scope_label=scope_label,
        scope_was_inferred=inferred,
        filters=resolved_filters,
        group_by=list(top.group_by),
        params=dict(top.params),
    )
