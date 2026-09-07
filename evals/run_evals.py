"""
Run the reconciliation set against every router and print the scorecard.

    python evals/run_evals.py                # replay recorded LLM responses
    python evals/run_evals.py --router rules
    python evals/run_evals.py --record       # call the API and re-record

The column that matters is WRONG NUMBER, not the hit rate. Hit rate can always
be raised by guessing more; a wrong number is what actually reaches a reader
and gets believed. Two things count as one:

  * answering when the correct response was a question or a refusal
  * answering with a metric other than the one asked for

Both hand over a confident figure that answers something the reader did not ask.

The same run writes docs/generated/examples.md, which the README includes.
Hand-written README examples are a note describing what the program used to do;
these cannot drift, because they are output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from nlq import answer as answer_mod
from nlq import ask as ask_mod
from nlq.db import Warehouse
from nlq.gates import decide
from nlq.router_llm import recorded_providers
from semantic import catalog as catalog_mod
from warehouse.build import build

FIXTURE_ROOT = REPO / "tests" / "fixtures"
# Same rows as the unit tests, separate file: DuckDB will not open a database
# for writing while another connection has it open, and the unit tests hold a
# read-only handle for the whole session.
FIXTURE_DB = REPO / "evals" / "fixture.duckdb"
QUESTIONS = Path(__file__).resolve().parent / "questions.yml"
GENERATED = REPO / "docs" / "generated" / "examples.md"

# Frozen anchor so "the last 30 days" means the same thing every run.
AS_OF = "2026-06-01"

def routers(record_provider: str | None = None) -> list[tuple[str, str]]:
    """One row per provider that has recordings, plus the rule router.

    Discovered from evals/cassettes/ rather than hardcoded: record a provider
    and its row appears; record none and the table shows only the rule router,
    with no empty rows implying numbers nobody measured.
    """
    names = list(recorded_providers())
    if record_provider and record_provider not in names:
        names.append(record_provider)
    return [(n, f"LLM: {n}") for n in names] + [("rules", "Saantorouter")]


class Result:
    def __init__(self, case, answer, decision, error=None):
        self.case = case
        self.answer = answer
        self.decision = decision
        self.error = error

    @property
    def expected(self) -> dict:
        return self.case["expect"]

    @property
    def got(self) -> str:
        return "ERROR" if self.error else self.answer.outcome.value

    @property
    def outcome_ok(self) -> bool:
        return self.got == self.expected["outcome"]

    @property
    def metric_ok(self) -> bool:
        wanted = self.expected.get("metric")
        if not wanted or self.got != "ANSWER":
            return True
        return self.answer.citation.get("metric") == wanted

    @property
    def hit(self) -> bool:
        return self.outcome_ok and self.metric_ok

    @property
    def wrong_number(self) -> bool:
        """Answered with a number that answers a different question."""
        if self.got != "ANSWER":
            return False
        return self.expected["outcome"] != "ANSWER" or not self.metric_ok


def run_router(router: str, cases: list[dict], record: bool) -> list[Result]:
    cat = catalog_mod.load()
    build(str(FIXTURE_DB), str(FIXTURE_ROOT), quiet=True)

    results = []
    with Warehouse(str(FIXTURE_DB)) as wh:
        for case in cases:
            try:
                proposal = ask_mod.route(case["q"], cat, wh, router,
                                         record=record, offline=not record)
                decision = decide(proposal, cat, wh, case["q"])
                answer = answer_mod.build(decision, cat, wh, as_of=AS_OF)
                results.append(Result(case, answer, decision))
            except Exception as exc:  # noqa: BLE001 - a crash must not read as a pass
                results.append(Result(case, None, None, error=exc))
    return results


def scorecard(by_router: dict[str, list[Result]], router_list) -> str:
    lines = [
        "Aineisto: tests/fixtures  (jaadytetty)      Tallenteet: evals/cassettes",
        f"Kysymyksia: {len(next(iter(by_router.values())))}",
        "",
        f"  {'':<16}{'osumat':>10}{'tarkennukset':>16}{'kieltaytymiset':>18}{'VAARIA LUKUJA':>17}",
    ]
    for key, label in router_list:
        rs = by_router.get(key)
        if rs is None:
            continue
        lines.append(
            f"  {label:<16}"
            f"{_frac(rs, lambda r: r.hit, lambda r: True):>10}"
            f"{_frac(rs, lambda r: r.hit, lambda r: r.expected['outcome'] == 'CLARIFY'):>16}"
            f"{_frac(rs, lambda r: r.hit, lambda r: r.expected['outcome'] == 'REFUSE'):>18}"
            f"{sum(r.wrong_number for r in rs):>17}"
        )
    lines += [
        "",
        "  VAARA LUKU = vastasi luvulla, kun oikea vastaus oli tarkennus tai",
        "  kieltaytyminen -- TAI vastasi eri mittarilla kuin kysyttiin.",
        "",
        "  Routerit eroavat siina, kuinka usein ne osuvat oikeaan mittariin.",
        "  Ne eivat eroa siina, mita porttien lapi paasee: portit ovat yhteiset.",
    ]
    return "\n".join(lines)


def _frac(results, hit_fn, filter_fn) -> str:
    subset = [r for r in results if filter_fn(r)]
    return f"{sum(1 for r in subset if hit_fn(r))}/{len(subset)}"


def misses(results: list[Result]) -> str:
    rows = [r for r in results if not r.hit]
    if not rows:
        return "  (ei poikkeamia)"
    out = []
    for r in rows:
        flag = "WRONG NUMBER" if r.wrong_number else "cautious"
        got = r.got
        if r.got == "ANSWER":
            got += f" / {r.answer.citation.get('metric')}"
        want = r.expected["outcome"]
        if r.expected.get("metric"):
            want += f" / {r.expected['metric']}"
        out.append(f"  [{flag:12}] {r.case['q']}\n{'':17}odotettu {want}\n{'':17}saatiin  {got}")
    return "\n".join(out)


def write_examples(results: list[Result], router_label: str) -> None:
    """README examples as build output. They cannot describe behaviour the
    program no longer has, because they are not written by hand."""
    picks = [
        ("Vastaus", next(r for r in results if r.got == "ANSWER" and r.hit)),
        ("Tarkennuspyynto", next(r for r in results if r.got == "CLARIFY" and r.hit)),
    ]
    picks += [
        (f"Kieltaytyminen: {r.decision.reason}", r)
        for r in results if r.got == "REFUSE" and r.hit
    ][:3]

    lines = [
        "<!-- GENERATED by evals/run_evals.py. Do not edit; edit the questions instead. -->",
        f"Router: {router_label}. Aineisto: tests/fixtures (jaadytetty).",
        "",
    ]
    for title, r in picks:
        lines += [
            f"### {title}",
            "",
            "```",
            f"$ python -m nlq.cli \"{r.case['q']}\"",
            "",
            r.answer.text,
            "```",
            "",
        ]
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    # Recording needs a key, and a key belongs in .env rather than in a shell
    # command that lands in history. .env is git-ignored.
    load_dotenv(REPO / ".env")

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--router", default="all",
                    help="all | rules | a provider name (anthropic, gemini, groq, ...)")
    ap.add_argument("--record", action="store_true", help="Call the API and record responses")
    args = ap.parse_args()

    cases = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))

    # When recording, the provider comes from LLM_PROVIDER (or the one key that
    # is set), so a first recording run has a row even before any cassette
    # exists.
    record_provider = None
    if args.record:
        from nlq import providers
        record_provider = args.router if args.router not in ("all", "rules") else providers.selected().name

    router_list = routers(record_provider)
    wanted = [k for k, _ in router_list] if args.router == "all" else [args.router]

    by_router: dict[str, list[Result]] = {}
    for key in wanted:
        try:
            by_router[key] = run_router(key, cases, args.record)
        except LookupError as exc:
            print(f"  {key}: skipped -- {exc}\n")

    print(scorecard(by_router, router_list))

    for key, label in router_list:
        if key in by_router:
            print(f"\n{label} -- poikkeamat:")
            print(misses(by_router[key]))

    # Prefer a model-routed run for the README examples; fall back to rules.
    llm_key = next((k for k, _ in router_list if k != "rules" and k in by_router), None)
    example_source = by_router.get(llm_key) if llm_key else by_router.get("rules")
    if example_source:
        label = llm_key or "saantopohjainen"
        write_examples(example_source, label)
        print(f"\n  Kirjoitettu: {GENERATED.relative_to(REPO)}")

    wrong = sum(r.wrong_number for rs in by_router.values() for r in rs)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
