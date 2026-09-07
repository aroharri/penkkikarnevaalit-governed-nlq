"""
Load, validate and compile the metric catalogue.

This module is the only place in the repo that produces SQL. Nothing else may
build a query string, and no caller may pass one in. That is what makes the
catalogue a lock rather than documentation of a lock.

Two guarantees are enforced here rather than left to callers to remember:

  1. No SQL is emitted without the metric's scope predicate. A query that
     reaches past its reporting boundary returns another group's numbers to
     this group's readers, so the failure mode is an exception, not a warning.
  2. Measures combined into one metric must share a base relation. Combining
     bases of different grain is the fan-out bug: one row joined to many, and
     the sum quietly doubles.

Both are checked when the catalogue loads, so a broken catalogue fails at
startup rather than in the middle of answering a question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CATALOG_DIR = Path(__file__).resolve().parent / "catalogs"

ALLOWED_AGGS = {"sum", "max", "min", "count", "avg"}


class CatalogError(Exception):
    """Raised when a catalogue is malformed. Always at load time, never later."""


class ScopeError(Exception):
    """Raised when a query would be compiled without its scope predicate."""


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    kind: str  # measure | ratio | difference
    scope: str
    grain: str
    unit: str
    note: str
    examples: list[str]
    allowed_dimensions: list[str]
    requires_params: list[str]
    base: str
    dataset: str
    parts: dict[str, str]  # measure names by role, e.g. {"numerator": "..."}
    source_file: str
    source_line: int

    @property
    def filterable_dimensions(self) -> list[str]:
        """Dimensions a question may filter on. The metric's own grain is always
        included: a lifter-grain metric must accept "...for Reino" without the
        catalogue restating it."""
        dims = list(self.allowed_dimensions)
        if self.grain == "lifter" and "lifter" not in dims:
            dims.append("lifter")
        return dims

    def definition(self, measures: dict[str, dict]) -> str:
        """Human-readable formula, for the citation. Built from the same fields
        the SQL is built from, so it cannot drift from what actually ran."""

        def expr(measure_name: str) -> str:
            m = measures[measure_name]
            return f"{m['agg'].upper()}({m['column']})"

        if self.kind == "measure":
            return expr(self.parts["measure"])
        if self.kind == "ratio":
            return f"{expr(self.parts['numerator'])} / {expr(self.parts['denominator'])}"
        if self.kind == "difference":
            return f"{expr(self.parts['minuend'])} - {expr(self.parts['subtrahend'])}"
        raise CatalogError(f"Unknown metric kind: {self.kind}")


@dataclass
class Catalog:
    datasets: dict[str, dict] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)

    # -- lookup -------------------------------------------------------------

    def metric_names(self) -> list[str]:
        return sorted(self.metrics)

    def get(self, name: str) -> Metric:
        if name not in self.metrics:
            raise CatalogError(f"No such metric: {name}")
        return self.metrics[name]

    def measures_for(self, metric: Metric) -> dict[str, dict]:
        return self.datasets[metric.dataset]["measures"]

    def dimension(self, metric: Metric, name: str) -> dict:
        return self.datasets[metric.dataset]["dimensions"][name]

    def entity(self, metric: Metric, name: str) -> dict:
        return self.datasets[metric.dataset]["entities"][name]

    # -- compilation --------------------------------------------------------

    def compile(
        self,
        metric_name: str,
        scope_value: str,
        filters: dict[str, str] | None = None,
        group_by: list[str] | None = None,
        params: dict[str, Any] | None = None,
        as_of: str | None = None,
    ) -> tuple[str, list]:
        """Build the SQL for one metric. The only SQL-producing path in the repo.

        `scope_value` is the key of the scope entity (e.g. a challenge_id) and
        is mandatory: passing None or "" raises rather than widening the query.
        """
        metric = self.get(metric_name)
        ds = self.datasets[metric.dataset]
        filters = dict(filters or {})
        group_by = list(group_by or [])
        params = dict(params or {})

        if not scope_value:
            raise ScopeError(
                f"Metric '{metric_name}' is scoped to {metric.scope} and cannot be "
                f"compiled without a scope value. Widening the query would report "
                f"other {metric.scope}s' rows."
            )

        for required in metric.requires_params:
            if required not in params:
                raise CatalogError(f"Metric '{metric_name}' requires parameter '{required}'.")

        # Grain columns. A lifter-grain metric always groups by lifter, so the
        # result cannot be read as a crew total by mistake.
        select_cols: list[str] = []
        group_cols: list[str] = []
        if metric.grain == "lifter":
            select_cols.append("lifter_name")
            group_cols.append("lifter_name")

        for dim_name in group_by:
            if dim_name not in metric.allowed_dimensions:
                raise CatalogError(
                    f"Dimension '{dim_name}' is not allowed on metric '{metric_name}'. "
                    f"Allowed: {metric.allowed_dimensions or 'none'}"
                )
            col = ds["dimensions"][dim_name]["column"]
            if col not in group_cols:
                select_cols.append(col)
                group_cols.append(col)

        value_sql = self._value_expression(metric, ds["measures"], params, as_of)

        scope_entity = ds["entities"][metric.scope]
        scope_col = scope_entity["key"]

        where = [f"{scope_col} = ?"]
        args: list[Any] = [scope_value]

        for key, val in filters.items():
            if key == metric.scope:
                continue  # already applied as the scope predicate
            if key not in metric.filterable_dimensions:
                raise CatalogError(
                    f"Filter '{key}' is not allowed on metric '{metric_name}'. "
                    f"Allowed: {metric.filterable_dimensions or 'none'}"
                )
            col = ds["dimensions"][key]["column"]
            where.append(f"lower({col}) = lower(?)")
            args.append(val)

        # The time window is applied inside the aggregate (see
        # _value_expression), so its arguments are bound before the WHERE
        # arguments -- the aggregate appears earlier in the statement.
        if "days" in metric.requires_params:
            window_args = ([as_of] if as_of else []) + [int(params["days"])]
            args = window_args + args

        base_sql = ds["bases"][metric.base]["sql"].rstrip()
        projection = ", ".join(select_cols + [f"{value_sql} as value"])
        sql = (
            f"select {projection}\n"
            f"from (\n{_indent(base_sql)}\n) base\n"
            f"where {' and '.join(where)}"
        )
        if group_cols:
            sql += f"\ngroup by {', '.join(group_cols)}\norder by {', '.join(group_cols)}"

        # Belt and braces. If a future edit ever drops the predicate, this
        # raises instead of silently returning a cross-challenge number.
        if f"{scope_col} = ?" not in sql:
            raise ScopeError(f"Compiled SQL for '{metric_name}' lost its scope predicate.")

        return sql, args

    @staticmethod
    def _value_expression(metric: Metric, measures: dict[str, dict],
                          params: dict | None = None, as_of: str | None = None) -> str:
        params = params or {}

        def agg(measure_name: str) -> str:
            m = measures[measure_name]
            window_col = m.get("window_column")
            if window_col and "days" in metric.requires_params:
                anchor = "?::date" if as_of else "current_date"
                inner = f"case when {window_col} >= {anchor} - ?::integer then {m['column']} end"
                return f"{m['agg']}({inner})"
            return f"{m['agg']}({m['column']})"

        if metric.kind == "measure":
            return agg(metric.parts["measure"])
        if metric.kind == "difference":
            return f"{agg(metric.parts['minuend'])} - {agg(metric.parts['subtrahend'])}"
        if metric.kind == "ratio":
            num, den = metric.parts["numerator"], metric.parts["denominator"]
            # nullif keeps a zero denominator from raising; the caller renders
            # the null as "not available" rather than as a number.
            return f"{agg(num)} / nullif({agg(den)}, 0) * 100"
        raise CatalogError(f"Unknown metric kind: {metric.kind}")


def _indent(sql: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in sql.splitlines())


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------

_PARTS_BY_KIND = {
    "measure": ["measure"],
    "ratio": ["numerator", "denominator"],
    "difference": ["minuend", "subtrahend"],
}


def load(catalog_dir: Path | str = CATALOG_DIR) -> Catalog:
    """Load every *.yml in the directory. Multi-catalogue from the start, so
    adding a second domain later needs no change here."""
    catalog_dir = Path(catalog_dir)
    files = sorted(catalog_dir.glob("*.yml"))
    if not files:
        raise CatalogError(
            f"No catalogue files in {catalog_dir}. Without a catalogue there are no "
            f"metrics, and no number can be produced. This is the intended behaviour."
        )

    cat = Catalog()
    for path in files:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
        _load_dataset(cat, raw, path, text)
    return cat


def _load_dataset(cat: Catalog, raw: dict, path: Path, text: str) -> None:
    ds_name = raw.get("dataset")
    if not ds_name:
        raise CatalogError(f"{path.name}: missing 'dataset'.")
    if ds_name in cat.datasets:
        raise CatalogError(f"{path.name}: dataset '{ds_name}' is already defined.")

    bases = raw.get("bases") or {}
    measures = raw.get("measures") or {}
    dimensions = raw.get("dimensions") or {}
    entities = raw.get("entities") or {}

    for name, m in measures.items():
        if m.get("base") not in bases:
            raise CatalogError(f"{path.name}: measure '{name}' names unknown base '{m.get('base')}'.")
        if m.get("agg") not in ALLOWED_AGGS:
            raise CatalogError(
                f"{path.name}: measure '{name}' has agg '{m.get('agg')}'. "
                f"Allowed: {sorted(ALLOWED_AGGS)}"
            )
        if not m.get("column"):
            raise CatalogError(f"{path.name}: measure '{name}' has no column.")

    cat.datasets[ds_name] = {
        "bases": bases,
        "measures": measures,
        "dimensions": dimensions,
        "entities": entities,
        "label": raw.get("label", ds_name),
    }

    for name, spec in (raw.get("metrics") or {}).items():
        cat.metrics[name] = _build_metric(name, spec, ds_name, bases, measures, dimensions,
                                          entities, path, text)


def _build_metric(name, spec, ds_name, bases, measures, dimensions, entities, path, text) -> Metric:
    kind = spec.get("kind")
    if kind not in _PARTS_BY_KIND:
        raise CatalogError(f"{path.name}: metric '{name}' has unknown kind '{kind}'.")

    parts = {}
    for role in _PARTS_BY_KIND[kind]:
        measure_name = spec.get(role)
        if measure_name not in measures:
            raise CatalogError(
                f"{path.name}: metric '{name}' names unknown measure '{measure_name}' as {role}."
            )
        parts[role] = measure_name

    # Fan-out guard: every measure in one metric must read the same base.
    used_bases = {measures[m]["base"] for m in parts.values()}
    if len(used_bases) > 1:
        raise CatalogError(
            f"{path.name}: metric '{name}' combines measures from bases {sorted(used_bases)}. "
            f"Their grains differ, so the join would fan out and double the sum."
        )
    base = used_bases.pop()

    scope = spec.get("scope")
    if not scope:
        raise CatalogError(
            f"{path.name}: metric '{name}' has no scope. Every metric needs a reporting "
            f"boundary; without one the query returns other groups' rows."
        )
    if scope not in entities:
        raise CatalogError(f"{path.name}: metric '{name}' scopes to unknown entity '{scope}'.")

    grain = spec.get("grain")
    if grain not in {"challenge", "lifter"}:
        raise CatalogError(f"{path.name}: metric '{name}' has unknown grain '{grain}'.")

    for dim in spec.get("allowed_dimensions") or []:
        if dim not in dimensions:
            raise CatalogError(f"{path.name}: metric '{name}' allows unknown dimension '{dim}'.")

    return Metric(
        name=name,
        label=spec.get("label", name),
        kind=kind,
        scope=scope,
        grain=grain,
        unit=spec.get("unit", ""),
        note=(spec.get("note") or "").strip(),
        examples=list(spec.get("examples") or []),
        allowed_dimensions=list(spec.get("allowed_dimensions") or []),
        requires_params=list(spec.get("requires_params") or []),
        base=base,
        dataset=ds_name,
        parts=parts,
        source_file=f"semantic/catalogs/{path.name}",
        source_line=_line_of(text, name),
    )


def _line_of(text: str, metric_name: str) -> int:
    """Line number of a metric definition, for the citation. A citation that
    points at a file but not a line makes the reader hunt."""
    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith(f"{metric_name}:"):
            return i
    return 0
