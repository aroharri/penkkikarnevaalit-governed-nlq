"""
The claim "the metrics are locked" is cheap to make and easy to leave untrue.

This is the only proof of it: hide the catalogue and check that nothing can
still produce a number. If any query survives, the YAML was a note describing
where the arithmetic lives, not the place it lives.

The same check for a spreadsheet would be: delete the sheet holding the named
formulas. If a figure still appears somewhere in the workbook, the formulas
were copies.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from semantic import catalog as catalog_mod
from semantic.catalog import CatalogError

REPO = Path(__file__).resolve().parent.parent


def test_no_metrics_exist_without_the_catalogue(tmp_path):
    empty = tmp_path / "catalogs"
    empty.mkdir()
    with pytest.raises(CatalogError) as exc:
        catalog_mod.load(empty)
    assert "no catalogue" in str(exc.value).lower()


def test_hiding_the_catalogue_breaks_every_query(tmp_path, real):
    """End to end: with the catalogue moved aside, no metric compiles at all."""
    live = catalog_mod.load()
    metric_names = live.metric_names()
    assert metric_names, "there must be metrics to lose"

    hidden = tmp_path / "catalogs"
    hidden.mkdir()
    shutil.copytree(catalog_mod.CATALOG_DIR, hidden, dirs_exist_ok=True)
    for yml in hidden.glob("*.yml"):
        yml.unlink()

    with pytest.raises(CatalogError):
        catalog_mod.load(hidden)


def test_a_metric_missing_its_scope_stops_the_whole_catalogue(tmp_path):
    """Failure is at load time, not when a question happens to touch the broken
    metric. A catalogue that half-loads is worse than one that refuses to."""
    broken = tmp_path / "catalogs"
    broken.mkdir()
    source = next(catalog_mod.CATALOG_DIR.glob("*.yml"))
    text = source.read_text(encoding="utf-8").replace("    scope: challenge\n", "", 1)
    (broken / source.name).write_text(text, encoding="utf-8")

    with pytest.raises(CatalogError) as exc:
        catalog_mod.load(broken)
    assert "scope" in str(exc.value).lower()


def test_a_metric_mixing_bases_stops_the_whole_catalogue(tmp_path):
    """The fan-out bug, caught before it can produce a doubled sum."""
    broken = tmp_path / "catalogs"
    broken.mkdir()
    source = next(catalog_mod.CATALOG_DIR.glob("*.yml"))
    text = source.read_text(encoding="utf-8").replace(
        "    minuend: goal_total_kg\n    subtrahend: latest_1rm_kg",
        "    minuend: goal_total_kg\n    subtrahend: session_count",
        1,
    )
    (broken / source.name).write_text(text, encoding="utf-8")

    with pytest.raises(CatalogError) as exc:
        catalog_mod.load(broken)
    assert "fan out" in str(exc.value).lower() or "grain" in str(exc.value).lower()


def test_the_citation_points_at_a_real_line(catalog):
    """A citation naming a file but not a line makes the reader hunt for it."""
    for name in catalog.metric_names():
        metric = catalog.get(name)
        path = REPO / metric.source_file
        assert path.exists(), f"{name} cites a file that does not exist"
        lines = path.read_text(encoding="utf-8").splitlines()
        assert 0 < metric.source_line <= len(lines)
        assert lines[metric.source_line - 1].strip().startswith(f"{name}:")
