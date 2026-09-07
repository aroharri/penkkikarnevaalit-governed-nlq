"""One question in, one decision out. Shared by the CLI and the evals."""

from __future__ import annotations

from nlq import answer as answer_mod
from nlq import providers, router_llm, router_rules
from nlq.db import Warehouse
from nlq.gates import Candidate, Proposal, decide
from semantic import catalog as catalog_mod


def default_router() -> str:
    """LLM when some provider has a key, rules otherwise, so a fresh clone runs."""
    return "llm" if any(p.has_key for p in providers.PROVIDERS.values()) else "rules"


def route(question: str, cat, warehouse, router: str = "rules", *,
          record: bool = False, offline: bool = False) -> Proposal:
    """`router` is either "rules" or a provider name ("llm" picks one by key)."""
    if router == "rules":
        return router_rules.route(question, cat, warehouse)
    provider = None if router == "llm" else router
    return router_llm.route(question, cat, warehouse, record=record, offline=offline,
                            provider=provider)


def answer_question(question: str, cat, warehouse, *, router: str = "rules",
                    as_of: str | None = None, force_metric: str | None = None,
                    record: bool = False, offline: bool = False,
                    metric_hint: str = answer_mod.CLI_HINT):
    """Question -> proposal -> gates -> answer, against an already-open warehouse.

    Split out from ask() so a session asking many questions opens the catalogue
    and the database once rather than once per question.
    """
    if force_metric:
        # --metric skips the router, not the gates. Naming a metric by hand is
        # allowed; bypassing scope or value checks is not.
        proposal = Proposal(candidates=[Candidate(metric=force_metric, confidence=1.0)],
                            raw={"router": "manual"})
    else:
        proposal = route(question, cat, warehouse, router, record=record, offline=offline)

    decision = decide(proposal, cat, warehouse, question)
    result = answer_mod.build(decision, cat, warehouse, as_of=as_of, metric_hint=metric_hint)
    return result, decision, proposal


def ask(question: str, *, router: str = "rules", catalog_dir=None, db_path=None,
        as_of: str | None = None, force_metric: str | None = None,
        record: bool = False, offline: bool = False):
    """One question, opening and closing everything around it."""
    cat = catalog_mod.load(catalog_dir) if catalog_dir else catalog_mod.load()
    with Warehouse(db_path) as wh:
        return answer_question(question, cat, wh, router=router, as_of=as_of,
                               force_metric=force_metric, record=record, offline=offline)
