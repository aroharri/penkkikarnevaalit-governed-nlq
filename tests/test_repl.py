"""
The interactive session, driven by a scripted `read` instead of a terminal.

Everything here is about the loop surviving: a session that dies on one bad
question is worse than no session, because the reader loses the thread of what
they were exploring.
"""

from __future__ import annotations

import pytest

from nlq import repl

REPO_DB = None  # the real warehouse; these tests assert behaviour, not numbers


def drive(lines, capsys, **kw):
    """Feed the loop a script and return everything it printed."""
    it = iter(lines)
    code = repl.run(router=kw.pop("router", "rules"), read=lambda _: next(it), **kw)
    return code, capsys.readouterr().out


def test_quit_exits_cleanly(capsys):
    code, out = drive([":quit"], capsys)
    assert code == 0
    assert "mittaria, router: rules" in out


def test_end_of_input_exits_like_quit(capsys):
    """Ctrl-D must not look like a crash."""
    def read(_):
        raise EOFError

    assert repl.run(router="rules", read=read) == 0


def test_ctrl_c_exits_without_a_traceback(capsys):
    def read(_):
        raise KeyboardInterrupt

    assert repl.run(router="rules", read=read) == 0


def test_a_question_is_answered_with_its_citation(capsys):
    _, out = drive(["Paljonko porukalta puuttuu tavoitteesta?", ":quit"], capsys)
    assert "crew_goal_gap_kg" in out
    assert "Rajaus:" in out
    assert "Katalogi" in out


def test_blank_lines_are_ignored(capsys):
    code, _ = drive(["", "   ", ":quit"], capsys)
    assert code == 0


def test_router_can_be_switched_mid_session(capsys):
    """The point of the session: ask, switch, ask again, see the difference."""
    _, out = drive([":router rules", ":quit"], capsys)
    assert "router: rules" in out


def test_show_prints_a_definition(capsys):
    _, out = drive([":show crew_goal_kg", ":quit"], capsys)
    assert "MAX(goal_total_1rm_kg)" in out


def test_show_of_an_unknown_metric_does_not_end_the_session(capsys):
    _, out = drive([":show ei_ole", "Paljonko porukalta puuttuu tavoitteesta?", ":quit"], capsys)
    assert "Ei mittaria" in out
    assert "crew_goal_gap_kg" in out, "the session must still answer afterwards"


def test_an_unknown_command_is_reported_not_treated_as_a_question(capsys):
    _, out = drive([":sekaisin", ":quit"], capsys)
    assert "tuntematon komento" in out


def test_metric_override_applies_once_only(capsys):
    """A forced metric that silently persisted would answer later questions
    with a metric the reader chose for an earlier one."""
    _, out = drive([
        ":metric crew_goal_kg",
        "yhdentekevaa",              # forced -> crew_goal_kg
        "Miten Reinolla menee?",     # not forced -> ambiguous, so a clarification
        ":quit",
    ], capsys)
    assert "crew_goal_kg" in out
    assert "Tarvitsen tarkennuksen" in out


def test_the_clarify_hint_is_the_one_that_works_here(capsys):
    """The CLI suggests a shell command. Inside a session that advice cannot be
    followed, and advice that cannot be followed where it is read is worse than
    none."""
    _, out = drive(["Mika on tavoite?", ":quit"], capsys)
    assert ":metric crew_goal_kg" in out
    assert "python -m nlq.cli --metric" not in out


def test_a_router_with_no_recording_keeps_the_session_alive(capsys):
    """Asking a model router something it has never been recorded answering is
    the normal case while exploring. It must explain itself, not exit."""
    _, out = drive([
        ":router anthropic",
        "taysin uusi kysymys jota ei ole nauhoitettu",
        ":router rules",
        "Paljonko porukalta puuttuu tavoitteesta?",
        ":quit",
    ], capsys)
    assert "No recorded response" in out or "Virhe" in out
    assert "crew_goal_gap_kg" in out, "the session must recover"


@pytest.mark.parametrize("command", [":help", ":h", ":?"])
def test_help_lists_the_commands(command, capsys):
    _, out = drive([command, ":quit"], capsys)
    assert ":show" in out and ":router" in out and ":quit" in out
