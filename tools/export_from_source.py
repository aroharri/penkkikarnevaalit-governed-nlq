"""
One-off export: production warehouse -> pseudonymised CSVs in data/.

The lifts are real. The names are not: every person and challenge gets a
pseudonym, and the mapping is written to tools/pseudonym_map.json, which
.gitignore keeps out of the repo. Re-running the script reproduces the same
CSVs, so `git diff` stays quiet unless the source data actually changed.

Deliberately exports EVERY user and EVERY challenge, including people who
belong to no challenge. Scoping is the metric's job, not the export's --
see docs/rajaus.md.

Usage:
    python tools/export_from_source.py --source ../penkkikarnevaalit-analytics/warehouse.duckdb
"""

import argparse
import csv
import json
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
MAP_FILE = REPO / "tools" / "pseudonym_map.json"

# Pseudonyms are assigned in a stable order (see assign_pseudonyms). They are
# deliberately different from the seed names used in penkkikarnevaalit-analytics
# so nobody reads the two repos as describing the same fictional people.
# Traditional Finnish men's names with a yard-flavoured second name. The fifth
# is assigned to whoever joined fifth, which in this export is the account that
# belongs to no challenge -- so "Ehdonalainen" (on parole) is the one who is not
# inside. That is a joke, and it is also the row every scope test depends on.
LIFTER_NAMES = [
    "Reino Kalteri",        # kalteri = the bars
    "Tauno Linna",          # linna = doing time
    "Veikko Rautanen",
    "Urho Muuri",
    "Kalle Ehdonalainen",   # on parole -- belongs to no challenge
    "Arvo Sakko",
    "Eino Vartio",
    "Sulo Putka",
]
CHALLENGE_NAMES = ["Kalterikarnevaalit 2026", "Kevathaaste", "Syyshaaste"]


def assign_pseudonyms(rows, names, prefix):
    """Stable id -> (short_id, display_name) map, ordered by creation time.

    Ordering by created_at rather than by the source UUID keeps the mapping
    stable when a row is edited, and keeps it independent of the UUIDs, which
    must not leak into the export at all.
    """
    ordered = sorted(rows, key=lambda r: (r["created_at"], str(r["id"])))
    mapping = {}
    for i, row in enumerate(ordered):
        if i >= len(names):
            raise SystemExit(f"Ran out of {prefix} pseudonyms: add more to the list.")
        mapping[str(row["id"])] = {"key": f"{prefix}{i + 1}", "name": names[i]}
    return mapping


def fetch(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.relative_to(REPO)}: {len(rows)} rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="Path to the source warehouse.duckdb")
    args = ap.parse_args()

    con = duckdb.connect(args.source, read_only=True)

    users = fetch(con, "select id, name, created_at::timestamp as created_at from raw.users")
    challenges = fetch(
        con,
        "select id, name, goal_kg, goal_start_date, goal_end_date, "
        "created_at::timestamp as created_at from raw.challenges",
    )
    members = fetch(
        con,
        "select challenge_id, user_id, target_1rm, starting_1rm, "
        "joined_at::timestamp as joined_at from raw.challenge_members",
    )
    # reps > 12 is outside Brzycki's reliable range. The rows are exported anyway
    # so the warehouse can count what it excluded; the exclusion is a documented
    # decision, not a silent filter. See semantic/catalogs/lifting.yml.
    lifts = fetch(
        con,
        "select id, user_id, weight_kg, reps, logged_at::date as lift_date "
        "from raw.workouts order by logged_at, id",
    )

    lifter_map = assign_pseudonyms(users, LIFTER_NAMES, "L")
    challenge_map = assign_pseudonyms(challenges, CHALLENGE_NAMES, "C")

    DATA.mkdir(exist_ok=True)

    write_csv(
        DATA / "lifters.csv",
        ["lifter_id", "lifter_name"],
        [
            {"lifter_id": lifter_map[str(u["id"])]["key"],
             "lifter_name": lifter_map[str(u["id"])]["name"]}
            for u in sorted(users, key=lambda r: (r["created_at"], str(r["id"])))
        ],
    )

    write_csv(
        DATA / "challenges.csv",
        ["challenge_id", "challenge_name", "goal_total_1rm_kg", "start_date", "end_date"],
        [
            {
                "challenge_id": challenge_map[str(c["id"])]["key"],
                "challenge_name": challenge_map[str(c["id"])]["name"],
                "goal_total_1rm_kg": c["goal_kg"],
                "start_date": c["goal_start_date"],
                "end_date": c["goal_end_date"],
            }
            for c in sorted(challenges, key=lambda r: (r["created_at"], str(r["id"])))
        ],
    )

    write_csv(
        DATA / "memberships.csv",
        ["challenge_id", "lifter_id", "target_1rm_kg", "starting_1rm_kg"],
        [
            {
                "challenge_id": challenge_map[str(m["challenge_id"])]["key"],
                "lifter_id": lifter_map[str(m["user_id"])]["key"],
                "target_1rm_kg": m["target_1rm"],
                "starting_1rm_kg": m["starting_1rm"],
            }
            for m in sorted(members, key=lambda r: (r["joined_at"], str(r["user_id"])))
        ],
    )

    write_csv(
        DATA / "lifts.csv",
        ["lift_id", "lifter_id", "lift_date", "weight_kg", "reps"],
        [
            {
                "lift_id": f"W{i + 1:03d}",
                "lifter_id": lifter_map[str(w["user_id"])]["key"],
                "lift_date": w["lift_date"],
                "weight_kg": w["weight_kg"],
                "reps": w["reps"],
            }
            for i, w in enumerate(lifts)
        ],
    )

    MAP_FILE.write_text(
        json.dumps({"lifters": lifter_map, "challenges": challenge_map}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n  Mapping written to {MAP_FILE.relative_to(REPO)} (git-ignored -- keep it local).")


if __name__ == "__main__":
    main()
