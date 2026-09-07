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


def test_the_menu_only_offers_names_the_system_can_answer_about(capsys, real):
    """A menu line the system will refuse is worse than a shorter menu.

    Every metric is scoped to a challenge, so a lifter who belongs to none is
    refused. Listing them as a suggestion promises something that cannot be
    delivered -- advice that fails where it is read.
    """
    assert main(["--menu"]) == 0
    out = capsys.readouterr().out

    orphans = real.run("""
        select l.lifter_name from dim_lifters l
        where not exists (select 1 from bridge_memberships m where m.lifter_id = l.lifter_id)
    """)
    names_line = next(ln for ln in out.splitlines() if ln.strip().startswith("Nostajat:"))
    for (orphan,) in orphans:
        assert orphan not in names_line, f"{orphan} is offered but belongs to no challenge"

    members = real.run("""
        select distinct l.lifter_name from dim_lifters l
        join bridge_memberships m on m.lifter_id = l.lifter_id
    """)
    for (member,) in members:
        assert member in names_line


def test_the_menu_is_built_from_the_catalogue_not_written_twice(capsys, catalog):
    """The example questions serve the model and the reader. If the menu had its
    own copy, one of them would go stale and nobody would notice which."""
    assert main(["--menu"]) == 0
    out = capsys.readouterr().out
    crew_examples = [e for n in catalog.metric_names()
                     if catalog.get(n).grain == "challenge"
                     for e in catalog.get(n).examples]
    assert crew_examples
    for example in crew_examples:
        assert example in out, f"catalogue example missing from the menu: {example}"
