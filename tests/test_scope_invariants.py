"""
Scope, against the real export. Not one hardcoded number in this file.

Scope failures go in two directions, and both are real reporting errors:

  OVER-SCOPING   the query reaches past the boundary and pulls in rows from
                 another challenge. The number is too big AND it puts one
                 group's figures in front of another group's readers.

  UNDER-SCOPING  an orphan row -- someone in the data but in no challenge --
                 drops out silently. The number is too small, and no
                 reconciliation catches it, because nobody computes both sides.

Everything here holds for any export: add a lifter, a challenge or a hundred
lifts and these still pass. That is the point of the file.
"""

from __future__ import annotations

import pytest

from semantic.catalog import ScopeError

CREW_METRICS = ["crew_total_1rm_kg", "crew_goal_gap_kg", "crew_target_fill_pct"]


def _challenges(warehouse):
    return [c for c, in warehouse.run("select challenge_id from dim_challenges")]


def test_every_metric_declares_a_scope(catalog):
    """Enforced at load time too, but stated here as a rule of the repo rather
    than an implementation detail of the loader."""
    for name in catalog.metric_names():
        assert catalog.get(name).scope, f"{name} has no reporting boundary"


def test_no_metric_can_compile_without_a_scope_value(catalog):
    """The guarantee that makes scope structural instead of remembered.

    Every metric either produces SQL carrying its scope predicate, or raises.
    There is no third outcome, so a future edit cannot quietly widen a query.
    """
    for name in catalog.metric_names():
        metric = catalog.get(name)
        params = {p: 30 for p in metric.requires_params}

        with pytest.raises(ScopeError):
            catalog.compile(name, scope_value="", params=params)

        sql, args = catalog.compile(name, scope_value="ANY", params=params)
        scope_col = catalog.entity(metric, metric.scope)["key"]
        assert f"{scope_col} = ?" in sql, f"{name} compiled without its scope predicate"
        assert "ANY" in args


def test_scoped_total_equals_that_challenges_members(real, catalog):
    """Recomputed independently of the catalogue: if the metric and a plain
    hand-written query disagree, one of them is wrong."""
    for challenge_id in _challenges(real):
        sql, args = catalog.compile("crew_total_1rm_kg", scope_value=challenge_id)
        from_metric = real.run(sql, args)[0][0] or 0

        independent = real.run("""
            select coalesce(sum(f.one_rm_kg), 0)
            from bridge_memberships m
            join fct_latest_lift f on f.lifter_id = m.lifter_id
            where m.challenge_id = ?
        """, [challenge_id])[0][0]

        assert from_metric == pytest.approx(independent)


def test_a_lifter_outside_every_challenge_reaches_no_metric(real, catalog):
    """Under-scoping in one direction, over-scoping in the other.

    Sum the metric across all challenges and compare with the sum over lifters
    who actually belong to one. Equal means the orphan neither leaked in nor
    took anything with them.
    """
    orphans = real.run("""
        select count(*) from dim_lifters l
        where not exists (select 1 from bridge_memberships m where m.lifter_id = l.lifter_id)
    """)[0][0]
    if orphans == 0:
        pytest.skip("no orphan lifters in the current export")

    across_challenges = 0.0
    for challenge_id in _challenges(real):
        sql, args = catalog.compile("crew_total_1rm_kg", scope_value=challenge_id)
        across_challenges += real.run(sql, args)[0][0] or 0

    members_only = real.run("""
        select coalesce(sum(f.one_rm_kg), 0)
        from bridge_memberships m
        join fct_latest_lift f on f.lifter_id = m.lifter_id
    """)[0][0]

    assert across_challenges == pytest.approx(members_only)

    # Whether this export's orphans have logged anything is not something the
    # test may assume -- today they have not. The leak case (an orphan whose
    # lifts would inflate the total if scope failed) is proven against the
    # frozen fixture instead, where Daavid's 150 kg is guaranteed to exist:
    # see test_metrics_math.test_an_orphans_lift_never_reaches_a_metric.
    everyone = real.run("select coalesce(sum(one_rm_kg), 0) from fct_latest_lift")[0][0]
    assert everyone >= members_only


def test_metric_grain_never_mixes_bases(catalog):
    """The fan-out guard. Combining measures whose grains differ would join one
    row to many and double the sum -- a wrong number that looks entirely
    plausible. The loader rejects it; this states it as a rule."""
    for name in catalog.metric_names():
        metric = catalog.get(name)
        measures = catalog.measures_for(metric)
        bases = {measures[m]["base"] for m in metric.parts.values()}
        assert len(bases) == 1, f"{name} mixes bases {sorted(bases)}"


def test_unknown_filters_and_dimensions_are_rejected(catalog):
    from semantic.catalog import CatalogError

    with pytest.raises(CatalogError):
        catalog.compile("crew_total_1rm_kg", scope_value="C1", filters={"gym": "Fitness24"})
    with pytest.raises(CatalogError):
        catalog.compile("crew_goal_gap_kg", scope_value="C1", group_by=["lifter"])
