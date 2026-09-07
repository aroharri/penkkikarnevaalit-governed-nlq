"""
Command line entry point.

    python -m nlq.cli "Paljonko porukalta puuttuu tavoitteesta?"
    python -m nlq.cli --router rules "..."
    python -m nlq.cli --metric crew_goal_gap_kg "..."     # skip the router, keep the gates
    python -m nlq.cli --json "..."
    python -m nlq.cli --list                              # the whole catalogue
"""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from nlq import ask as ask_mod
from semantic import catalog as catalog_mod


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, which cannot encode every character
    # used here. Reconfiguring keeps output identical across platforms.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    ap = argparse.ArgumentParser(prog="nlq", description="Governed NLQ over a locked metric catalogue")
    ap.add_argument("question", nargs="?", help="Question in plain language")
    ap.add_argument("--router", choices=["llm", "rules"], default=None,
                    help="Default: llm when ANTHROPIC_API_KEY is set, otherwise rules")
    ap.add_argument("--metric", help="Name a metric directly. Skips the router, not the gates.")
    ap.add_argument("--as-of", help="Anchor date for time windows (YYYY-MM-DD). Default: today.")
    ap.add_argument("--json", action="store_true", help="Machine-readable output, citation included")
    ap.add_argument("--list", action="store_true", help="List the catalogue and exit")
    ap.add_argument("--record", action="store_true", help="Call the API and record the response")
    args = ap.parse_args(argv)

    if args.list:
        return _print_catalog()

    if not args.question:
        ap.error("a question is required (or use --list)")

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


if __name__ == "__main__":
    sys.exit(main())
