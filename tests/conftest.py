"""
Shared fixtures.

Two kinds of test data, and the split is deliberate:

  * The FROZEN fixture (tests/fixtures) has hand-computed expected values
    written into the tests as literal numbers. It never changes, so those
    numbers stay correct forever. It proves the arithmetic.

  * The REAL export (data/) changes whenever someone logs a lift or joins a
    challenge. Tests against it assert invariants only -- statements true of
    any data at all. It proves the structure.

A hardcoded expectation checked against live data is a time bomb: the sixth
lifter turns a test red while nothing is actually broken.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from nlq.db import Warehouse
from semantic import catalog as catalog_mod
from warehouse.build import build

# Anchors every time window, so a test asking about "the last 60 days" means
# the same thing next year as it does today.
AS_OF = "2026-06-01"


def _built(root: Path, name: str) -> str:
    db = root / name
    build(str(db), str(root), quiet=True)
    return str(db)


@pytest.fixture(scope="session")
def catalog():
    return catalog_mod.load()


@pytest.fixture(scope="session")
def frozen(tmp_path_factory):
    """One challenge, two members, one orphan, one set outside the rep range."""
    path = _built(REPO / "tests" / "fixtures", "fixture.duckdb")
    with Warehouse(path) as wh:
        yield wh


@pytest.fixture(scope="session")
def frozen_multi():
    """Two challenges -- the only fixture where scope cannot be inferred."""
    path = _built(REPO / "tests" / "fixtures_multi", "fixture.duckdb")
    with Warehouse(path) as wh:
        yield wh


@pytest.fixture(scope="session")
def real():
    """The actual export. Invariant assertions only -- never a literal number."""
    db = REPO / "warehouse.duckdb"
    if not db.exists():
        build(str(db), str(REPO), quiet=True)
    with Warehouse(str(db)) as wh:
        yield wh


def value(warehouse, catalog, metric, scope="X1", **kwargs):
    """Compile and run one metric, returning the single scalar result."""
    sql, args = catalog.compile(metric, scope_value=scope, **kwargs)
    rows = warehouse.run(sql, args)
    assert len(rows) == 1, f"{metric} returned {len(rows)} rows, expected 1"
    return rows[0][-1]
