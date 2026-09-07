"""
Turn a decision into an answer a person can check.

Every ANSWER carries its citation: which metric, its formula, the grain, the
scope, and the file and line the definition lives on. That is not politeness.
It is what makes one answer composable with the next -- a number that arrives
with its definition can be built on; a number that arrives as prose can only
be believed.

Scope is printed on the FIRST line, including when it was inferred, because a
reader who does not know what was excluded cannot judge the number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nlq.gates import Decision, Outcome
from semantic.catalog import Catalog

BAR = "-" * 66


@dataclass
class Answer:
    outcome: Outcome
    text: str
    rows: list[tuple] = field(default_factory=list)
    citation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "text": self.text,
            "rows": [list(r) for r in self.rows],
            "citation": self.citation,
        }


# How to name a metric by hand. Differs between the one-shot CLI and an
# interactive session, and advice that cannot be followed where it is read is
# worse than none.
CLI_HINT = 'python -m nlq.cli --metric {metric} "..."'
REPL_HINT = ":metric {metric}"


def build(decision: Decision, catalog: Catalog, warehouse, as_of: str | None = None,
          metric_hint: str = CLI_HINT) -> Answer:
    if decision.outcome is Outcome.REFUSE:
        return _refusal(decision, catalog)
    if decision.outcome is Outcome.CLARIFY:
        return _clarification(decision, catalog, metric_hint)
    return _answer(decision, catalog, warehouse, as_of)


# ---------------------------------------------------------------------------


def _refusal(decision: Decision, catalog: Catalog) -> Answer:
    lines = [f"En vastaa: {decision.message}"]
    if decision.reason == "no_metric":
        lines.append("")
        lines.append("Osaan nama mittarit:")
        for name in decision.alternatives:
            lines.append(f"  {name:30} {catalog.get(name).label}")
    if decision.reason == "unknown_value":
        # Spelling this out matters: an empty result and a zero both look like
        # answers, and a reader has no way to tell them from a real number.
        lines.append("En palauta nollaa enka tyhjaa tulosta -- molemmat nayttaisivat luvulta.")
    return Answer(Outcome.REFUSE, "\n".join(lines), citation={"reason": decision.reason})


def _clarification(decision: Decision, catalog: Catalog, metric_hint: str) -> Answer:
    lines = [f"Tarvitsen tarkennuksen: {decision.message}"]
    if decision.alternatives:
        lines.append("")
        for i, name in enumerate(decision.alternatives, start=1):
            if name in catalog.metrics:
                lines.append(f"  {i}  {name:30} {catalog.get(name).label}")
            else:
                lines.append(f"  {i}  {name}")
    if decision.reason == "ambiguous":
        lines.append("")
        lines.append("En valitse puolestasi. Kysy tarkemmin, tai nimea mittari suoraan:")
        lines.append("  " + metric_hint.format(metric=decision.alternatives[0]))
    return Answer(Outcome.CLARIFY, "\n".join(lines), citation={"reason": decision.reason})


def _answer(decision: Decision, catalog: Catalog, warehouse, as_of: str | None) -> Answer:
    metric = decision.metric
    sql, args = catalog.compile(
        metric.name,
        scope_value=decision.scope_value,
        filters=decision.filters,
        group_by=decision.group_by,
        params=decision.params,
        as_of=as_of,
    )
    rows = warehouse.run(sql, args)
    if not rows:
        return _empty_result(decision, catalog, warehouse)

    inferred = "  (ainoa datassa -- ratkaistu automaattisesti)" if decision.scope_was_inferred else ""
    lines = [f"Rajaus: {decision.scope_label}{inferred}", ""]

    for row in rows:
        label = " / ".join(str(v) for v in row[:-1])
        lines.append(f"  {label:<34}{_fmt(row[-1], metric.unit):>14}")

    # The measured/estimated split, whenever the number is a sum of 1RMs. The
    # total hides that two different kinds of number were added together.
    split = _source_split(decision, catalog, warehouse)
    if split:
        lines.append("")
        total = sum(v for _, v in split) or 1
        for source, value in split:
            share = value / total * 100
            lines.append(f"    {_SOURCE_LABEL[source]:<32}{_fmt(value, 'kg'):>14}   {share:.0f} %")

    measures = catalog.measures_for(metric)
    citation = {
        "metric": metric.name,
        "label": metric.label,
        "definition": metric.definition(measures),
        "grain": metric.grain,
        "scope": f"{metric.scope} = {decision.scope_value}",
        "scope_label": decision.scope_label,
        "scope_inferred": decision.scope_was_inferred,
        "filters": decision.filters,
        "params": decision.params,
        "note": " ".join(metric.note.split()),
        "source": f"{metric.source_file}:{metric.source_line}",
        "sql": sql,
    }

    lines += ["", f"- Lahde {BAR[:58]}"]
    lines.append(f"  Mittari       {metric.name}")
    lines.append(f"  Maaritelma    {citation['definition']}")
    lines.append(f"  Rakeisuus     {metric.grain}")
    lines.append(f"  Rajaukset     {citation['scope']}" +
                 (f", {decision.filters}" if decision.filters else ""))
    if decision.params:
        lines.append(f"  Parametrit    {decision.params}")
    lines.append(f"  Jasenia       {_member_note(decision, catalog, warehouse)}")
    if citation["note"]:
        lines.append(f"  Huom          {_wrap(citation['note'])}")
    lines.append(f"  Katalogi      {citation['source']}")

    return Answer(Outcome.ANSWER, "\n".join(lines), rows=rows, citation=citation)


def _empty_result(decision: Decision, catalog: Catalog, warehouse) -> Answer:
    """No rows is not a number, and must not be dressed as one.

    An empty table under a citation reads as an answer -- the reader sees a
    metric, a formula and a scope, and concludes the value is nothing. The
    common cause is a filter that is valid on its own but empty in combination:
    a real person who is not in this challenge, a real cost centre with no
    postings in the period. Naming which half of the combination emptied it is
    the difference between "no data" and "wrong question".
    """
    metric = decision.metric
    lines = [(f"En vastaa: rajaus {decision.scope_label} ei sisalla yhtaan rivia "
              f"mittarille {metric.name}.")]

    lifter = decision.filters.get("lifter")
    if lifter:
        entity = catalog.entity(metric, "lifter")
        exists = warehouse.run(
            f"select count(*) from {entity['table']} "
            f"where lower({entity['label_column']}) = lower(?)", [lifter])[0][0]
        if exists:
            lines.append(
                f"\"{lifter}\" on datassa, mutta ei kuulu haasteeseen "
                f"{decision.scope_label}. Mittari on rajattu haasteen sisalle, joten "
                f"han ei nay siina -- eika tyhja tulos ole han nolla."
            )
    lines.append("En palauta nollaa enka tyhjaa taulukkoa -- molemmat nayttaisivat luvulta.")
    return Answer(Outcome.REFUSE, "\n".join(lines), citation={"reason": "empty_result"})


_SOURCE_LABEL = {
    "true_max": "josta oikeaa ykkosmaksimia",
    "brzycki_estimate": "     laskennallista",
}


def _source_split(decision: Decision, catalog: Catalog, warehouse) -> list[tuple[str, float]]:
    """Split a single total into real maxima and Brzycki estimates.

    Only for a challenge-grain metric, i.e. one number. At lifter grain the
    compiled query still groups by lifter, so collapsing its rows by source
    would keep one arbitrary lifter per source -- a pair of numbers that add up
    to nothing in particular and sit directly under a total they do not
    explain. (They did, briefly. A displayed number that is not a quantity is
    the failure this whole repo argues against, so it is stated here rather
    than quietly patched.)

    The split is also meaningless per lifter: one lifter's latest set has
    exactly one source, so the "breakdown" would just repeat the row.
    """
    metric = decision.metric
    if metric.grain != "challenge":
        return []
    if "one_rm_source" not in metric.allowed_dimensions or "one_rm_source" in decision.group_by:
        return []
    sql, args = catalog.compile(
        metric.name,
        scope_value=decision.scope_value,
        filters=decision.filters,
        group_by=["one_rm_source"],
    )
    rows = warehouse.run(sql, args)
    order = ["true_max", "brzycki_estimate"]
    by_source = {r[-2]: r[-1] for r in rows if r[-1] is not None}
    return [(s, by_source[s]) for s in order if s in by_source]


def _member_note(decision: Decision, catalog: Catalog, warehouse) -> str:
    """How many people the number covers, and how many it does not.

    An orphan -- someone in the data but in no challenge -- contributes to
    nothing. That is correct, and saying it out loud is the difference between
    a scoped number and a number that quietly lost rows.
    """
    total = warehouse.run("select count(*) from dim_lifters")[0][0]
    members = warehouse.run(
        "select count(*) from bridge_memberships where challenge_id = ?",
        [decision.scope_value],
    )[0][0]
    outside = total - members
    note = f"{members}"
    if outside:
        note += f"  (datassa {total} kayttajaa; {outside} ei kuulu tahan haasteeseen, ei mukana)"
    return note


def _fmt(value, unit: str) -> str:
    if value is None:
        return "ei saatavilla"
    if unit == "pct":
        return f"{value:,.1f} %".replace(",", " ")
    if unit == "count":
        return f"{value:,.0f}".replace(",", " ")
    return f"{value:,.1f} kg".replace(",", " ")


def _wrap(text: str, width: int = 62, indent: str = " " * 16) -> str:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    lines.append(current)
    return f"\n{indent}".join(lines)
