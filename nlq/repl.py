"""
Interactive session: ask, read, ask again.

One question per shell command is fine for a script and poor for exploring,
which is what a reader actually wants to do -- the interesting thing here is
not that one question works, it is what the tenth one does when you deliberately
make it vague.

The catalogue and the database are opened once for the session instead of once
per question, which is also why :router can switch mid-session: asking the same
question through both routers back to back is the reconciliation table in
miniature, and it is more convincing seen than read.
"""

from __future__ import annotations

import sys

from nlq import answer as answer_mod
from nlq import ask as ask_mod
from nlq.cli import menu_text
from nlq.db import Warehouse
from semantic import catalog as catalog_mod

PROMPT = "nlq> "

HELP = """
  Kirjoita kysymys suomeksi, tai:

    :menu              mita voit kysya, tavallisella kielella
    :list              mittarit yhtena listana
    :show <mittari>    yhden mittarin maaritelma  (:show all = kaikki)
    :router <nimi>     vaihda router: rules | llm | anthropic | gemini | ...
    :metric <nimi>     seuraava kysymys pakotetaan tahan mittariin
    :json              nayta lahdeviite koneluettavana (paalle/pois)
    :help              tama
    :quit              ulos  (myos Ctrl-D)

  Kokeile naita -- ne osuvat eri portteihin:

    Paljonko porukalta puuttuu tavoitteesta?
    Miten Reinolla menee?                     -> tarkennus, kolme lukemaa
    Mika on tavoite?                          -> tarkennus, kaksi tavoitelukua
    Mika on Kallen nykyinen ykkosmaksimi?     -> kieltaytyminen, ei haasteessa
    Miten Pekalla menee?                      -> kieltaytyminen, ei datassa
    Kuka on vahvin kaikista kayttajista?      -> kieltaytyminen, ylittaa rajan
"""


def run(router: str | None = None, as_of: str | None = None,
        read=input, db_path: str | None = None, offline: bool = False) -> int:
    """`read` is injected so the loop can be driven by a test without a tty.

    `offline` refuses to call a provider even when a key is present: an
    unrecorded question then says so instead of quietly becoming a paid
    request. A person at a prompt wants the opposite, so it defaults to False.
    """
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    cat = catalog_mod.load()
    router = router or ask_mod.default_router()
    as_json = False
    force_metric: str | None = None

    with Warehouse(db_path) as wh:
        # The first thing a reader sees must not be an empty prompt. Three
        # lines they can copy beat a blank line and a blinking cursor.
        print(f"{len(cat.metrics)} mittaria, router: {router}.  "
              f":menu = mita voi kysya  |  :help  |  :quit")
        print()
        for line in _teaser(cat, wh):
            print(f"  {line}")
        print()

        while True:
            try:
                line = read(PROMPT)
            except (EOFError, KeyboardInterrupt):
                print()
                return 0

            line = (line or "").strip()
            if not line:
                continue

            if line.startswith(":"):
                command, _, argument = line[1:].partition(" ")
                command, argument = command.strip().lower(), argument.strip()

                if command in ("quit", "q", "exit"):
                    return 0
                if command in ("help", "h", "?"):
                    print(HELP)
                elif command == "menu":
                    print()
                    print(menu_text(cat, wh))
                    print()
                elif command == "list":
                    _list(cat)
                elif command == "show":
                    _show(cat, argument)
                elif command == "router":
                    router = argument or router
                    print(f"  router: {router}")
                elif command == "metric":
                    force_metric = argument or None
                    print(f"  seuraava kysymys -> {force_metric or '(router paattaa)'}")
                elif command == "json":
                    as_json = not as_json
                    print(f"  json: {'paalla' if as_json else 'pois'}")
                else:
                    print(f"  tuntematon komento :{command}   (:help)")
                continue

            _answer(line, cat, wh, router, as_of, force_metric, as_json, offline)
            force_metric = None  # one question only, so it cannot leak silently


def _answer(question, cat, wh, router, as_of, force_metric, as_json, offline=False) -> None:
    try:
        result, decision, _ = ask_mod.answer_question(
            question, cat, wh, router=router, as_of=as_of, force_metric=force_metric,
            metric_hint=answer_mod.REPL_HINT, offline=offline,
        )
    except LookupError as exc:
        # No recorded response for this question. Expected while exploring with
        # a model router and no key: say so and keep the session alive rather
        # than dropping the reader back to the shell.
        print(f"\n  {exc}\n  Kokeile: :router rules\n")
        return
    except Exception as exc:  # noqa: BLE001 - a session must survive one bad question
        print(f"\n  Virhe: {type(exc).__name__}: {exc}\n")
        return

    print()
    if as_json:
        import json
        print(json.dumps({"router": router, "reason": decision.reason, **result.to_dict()},
                         indent=2, ensure_ascii=False, default=str))
    else:
        print(result.text)
    print()


def _teaser(cat, wh) -> list[str]:
    """Three questions that work, straight away.

    Not a summary of the menu -- a sample of it. Someone who copies one of these
    has used the thing inside ten seconds, which is the only way a question
    interface ever gets adopted.
    """
    lines = [ln.strip() for ln in menu_text(cat, wh).splitlines()
             if ln.startswith("  ") and ln.strip().endswith("?")]
    return lines[:2] + lines[-1:]


def _list(cat) -> None:
    for name in cat.metric_names():
        m = cat.get(name)
        print(f"  {name:30} {m.label}")


def _show(cat, which: str) -> None:
    from nlq.cli import _render_metric

    if not which:
        print("  :show <mittari>   tai   :show all")
        return
    names = cat.metric_names() if which == "all" else [which]
    for name in names:
        if name not in cat.metrics:
            print(f"  Ei mittaria '{name}'.  :list nayttaa mita on.")
            return
    print()
    for i, name in enumerate(names):
        if i:
            print()
        _render_metric(cat, cat.get(name))
    print()
