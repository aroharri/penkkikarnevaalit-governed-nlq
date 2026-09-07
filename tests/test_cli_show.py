"""
--show, the reading side of the lock.

semantic/catalog.py claims the definition is something a controller can read
and dispute. That claim needs a way to read it that is not "open the YAML and
know where to look" -- otherwise it is a note about governance rather than
governance. These tests hold it to that.
"""

from __future__ import annotations

import pytest

from nlq.cli import main


def test_show_prints_the_formula_not_just_the_label(capsys, catalog):
    assert main(["--show", "crew_total_1rm_kg"]) == 0
    out = capsys.readouterr().out

    assert "SUM(one_rm_kg)" in out, "the formula is the whole point"
    assert "latest_1rm_kg = sum(one_rm_kg)" in out, "and where it reads from"
    assert "member_current" in out


def test_show_states_the_scope_as_mandatory(capsys):
    assert main(["--show", "crew_goal_gap_kg"]) == 0
    out = capsys.readouterr().out
    assert "challenge" in out
    assert "pakollinen" in out


def test_show_carries_the_decision_note(capsys):
    """The note records a decision -- which of two competing numbers is the
    number. A reader who cannot see it cannot dispute it."""
    assert main(["--show", "crew_target_fill_pct"]) == 0
    out = capsys.readouterr().out
    assert "NON-ADDITIVE" in out
    assert "tests/test_metrics_math.py" in out


def test_show_cites_a_line_a_reader_can_open(capsys, catalog):
    assert main(["--show", "lifter_target_gap_kg"]) == 0
    out = capsys.readouterr().out
    metric = catalog.get("lifter_target_gap_kg")
    assert f"{metric.source_file}:{metric.source_line}" in out


def test_show_all_covers_every_metric(capsys, catalog):
    assert main(["--show", "all"]) == 0
    out = capsys.readouterr().out
    for name in catalog.metric_names():
        assert name in out, f"{name} missing from --show all"


def test_show_ratio_names_both_ingredients(capsys):
    assert main(["--show", "crew_goal_fill_pct"]) == 0
    out = capsys.readouterr().out
    assert "numerator" in out and "denominator" in out


def test_an_unknown_metric_lists_the_real_ones(capsys, catalog):
    """No fuzzy matching here either. Naming the alternatives beats guessing
    which one was meant."""
    assert main(["--show", "crew_total"]) == 3
    out = capsys.readouterr().out
    assert "Ei mittaria" in out
    assert "crew_total_1rm_kg" in out


@pytest.mark.parametrize("flag", [["--list"], ["--providers"]])
def test_informational_flags_need_no_question_and_no_warehouse(flag, capsys):
    assert main(flag) == 0
    assert capsys.readouterr().out.strip()
