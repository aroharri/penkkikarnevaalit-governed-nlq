"""
Command line entry point.

    python -m nlq.cli "Paljonko porukalta puuttuu tavoitteesta?"
    python -m nlq.cli --router rules "..."
    python -m nlq.cli --metric crew_goal_gap_kg "..."     # skip the router, keep the gates
    python -m nlq.cli --json "..."
    python -m nlq.cli --list                              # one line per metric
    python -m nlq.cli --show crew_total_1rm_kg            # one definition in full
    python -m nlq.cli --show all                          # every definition
    python -m nlq.cli                                     # interactive session
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from nlq import ask as ask_mod
from semantic import catalog as catalog_mod

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, which cannot encode every character
    # used here. Reconfiguring keeps output identical across platforms.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    # Explicit path, not a search from the working directory. Otherwise
    # running from elsewhere finds no key and silently falls back to the
    # rule router -- and which model answered would depend on where the
    # reader happened to be standing.
    load_dotenv(REPO / ".env")
    ap = argparse.ArgumentParser(prog="nlq", description="Governed NLQ over a locked metric catalogue")
    ap.add_argument("question", nargs="?", help="Question in plain language")
    ap.add_argument("--router", default=None,
                    help="rules | llm | a provider name (anthropic, gemini, groq, xai, "
                         "openrouter, ollama). Default: llm when any provider has a key, "
                         "otherwise rules.")
    ap.add_argument("--metric", help="Name a metric directly. Skips the router, not the gates.")
    ap.add_argument("--as-of", help="Anchor date for time windows (YYYY-MM-DD). Default: today.")
    ap.add_argument("--json", action="store_true", help="Machine-readable output, citation included")
    ap.add_argument("--list", action="store_true", help="One line per metric, then exit")
    ap.add_argument("--show", metavar="METRIC",
                    help="Full definition of one metric, or 'all' for every metric. "
                         "Same fields an answer cites, without having to invent a question first.")
    ap.add_argument("--repl", action="store_true",
                    help="Interactive session. Also the default when no question is given.")
    ap.add_argument("--providers", action="store_true", help="List LLM providers and exit")
    ap.add_argument("--record", action="store_true", help="Call the API and record the response")
    args = ap.parse_args(argv)

    if args.list:
        return _print_catalog()

    if args.show:
        return _print_metric(args.show)

    if args.providers:
        return _print_providers()

    # No question and no flag means the reader wants to explore, not to have
    # argparse explain itself.
    if args.repl or not args.question:
        from nlq import repl
        return repl.run(router=args.router, as_of=args.as_of)

    router = args.router or ask_mod.default_router()
    result, decision, _proposal = ask_mod.ask(
        args.question,
        router=router,
        as_of=args.as_of,
        force_metric=args.metric,
        record=args.record,
    )

    if args.json:
        print(json.dumps({
            "question": args.question,
            "router": router,
            "reason": decision.reason,
            **result.to_dict(),
        }, indent=2, ensure_ascii=False, default=str))
    else:
        print(result.text)

    # Exit codes let a script tell the three outcomes apart without parsing text.
    return {"ANSWER": 0, "CLARIFY": 2, "REFUSE": 3}[result.outcome.value]


def _print_catalog() -> int:
    cat = catalog_mod.load()
    print(f"{len(cat.metrics)} metrics. Every formula lives in semantic/catalogs/.\n")
    for name in cat.metric_names():
        m = cat.get(name)
        print(f"  {name}")
        print(f"      {m.label}   [{m.grain}, {m.unit}, scope: {m.scope}]")
        if m.requires_params:
            print(f"      requires: {', '.join(m.requires_params)}")
    return 0


def _print_metric(which: str) -> int:
    """Print a metric the way the answer cites it.

    semantic/catalog.py says the definition has to be something a controller can
    read and dispute. That was only half true: the definition existed in YAML,
    but the only way to see a formula was to open the file and know where to
    look. A definition nobody can read is not governance, it is a note about
    governance -- the same post-it/lock distinction, one level up.

    Field labels match the citation printed under an answer exactly, so the two
    are recognisably the same object seen from two directions.
    """
    cat = catalog_mod.load()
    names = cat.metric_names() if which == "all" else [which]

    unknown = [n for n in names if n not in cat.metrics]
    if unknown:
        print(f"Ei mittaria '{unknown[0]}'.\n\nKatalogissa on:")
        for name in cat.metric_names():
            print(f"  {name}")
        return 3

    for i, name in enumerate(names):
        if i:
            print()
        _render_metric(cat, cat.get(name))
    return 0


def _render_metric(cat, m) -> None:
    measures = cat.measures_for(m)
    print(f"{m.name}")
    print(f"  {m.label}")
    print()
    print(f"  Maaritelma    {m.definition(measures)}")

    # The ingredients, so the chain from stored fact to reported number is
    # visible in one screen. The formula alone still hides where it reads from.
    for role, measure_name in m.parts.items():
        spec = measures[measure_name]
        print(f"     {role:<12}{measure_name} = {spec['agg']}({spec['column']})"
              f"  <- {spec['base']}")

    print(f"  Rakeisuus     {m.grain}")
    print(f"  Yksikko       {m.unit}")
    print(f"  Rajaus        {m.scope}  (pakollinen -- ilman sita ei synny SQL:aa)")
    print(f"  Sallitut      rajaukset: {', '.join(m.filterable_dimensions) or '-'}")
    print(f"                ryhmittelyt: {', '.join(m.allowed_dimensions) or '-'}")
    if m.requires_params:
        print(f"  Vaatii        {', '.join(m.requires_params)}")
    if m.note:
        print(f"  Huom          {_wrap(' '.join(m.note.split()))}")
    if m.examples:
        print("  Esimerkkeja   " + f"\n{' ' * 16}".join(m.examples))
    print(f"  Katalogi      {m.source_file}:{m.source_line}")


def _wrap(text: str, width: int = 60, indent: str = " " * 16) -> str:
    lines, current = [], ""
    for word in text.split():
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    lines.append(current)
    return f"\n{indent}".join(lines)


def _print_providers() -> int:
    from nlq import providers
    from nlq.router_llm import recorded_providers

    recorded = set(recorded_providers())
    print("Provider     key set  recorded  model")
    for p in providers.PROVIDERS.values():
        print(f"  {p.name:<11}{'yes' if p.has_key else ' - ':>6}"
              f"{'yes' if p.name in recorded else ' - ':>10}   {p.model}")
        if p.note:
            print(f"      {p.note}")
    print()
    print("The rule router needs no key at all:  --router rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
