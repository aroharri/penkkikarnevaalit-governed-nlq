"""
Build the local DuckDB warehouse from data/*.csv.

Idempotent: every statement is CREATE OR REPLACE, so running it twice is the
same as running it once. Makes no assumption about how many lifters,
challenges or lifts exist -- add a row to a CSV and rebuild.

Usage:
    python warehouse/build.py
"""

import os
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
DB_PATH = os.environ.get("DUCKDB_PATH", "warehouse.duckdb")


def build(db_path: str = DB_PATH, data_root: str | Path = REPO, quiet: bool = False) -> None:
    """Build into db_path from <data_root>/data/*.csv.

    data_root is a parameter so the frozen fixtures in tests/ are built by this
    same function. A test harness that loads data its own way would be testing
    the harness, not the build.
    """
    # Resolve before the chdir, so a relative db_path still lands where the
    # caller meant it to.
    db_path = str(Path(db_path).resolve())
    previous_cwd = os.getcwd()
    try:
        # schema.sql reads data/*.csv by relative path, so run from the data root.
        os.chdir(data_root)
        con = duckdb.connect(db_path)
        try:
            con.execute(SCHEMA.read_text(encoding="utf-8"))
        except duckdb.Error as exc:
            # Failing here is correct -- a malformed CSV must not load
            # half-parsed. But DuckDB's message is about parser internals, so
            # say what a person can actually act on.
            raise SystemExit("\n".join([
                f"Could not load the CSVs in {Path(data_root).resolve() / 'data'}.",
                "",
                f"  {exc}",
                "",
                "The schema is declared in warehouse/schema.sql rather than sniffed",
                "from the file, so the usual causes are:",
                "  - a column renamed, missing, or in a different order",
                "  - a value that will not cast (text in a numeric column, a bad date)",
                "  - mixed line endings, usually from appending to the file by hand",
            ])) from exc
    finally:
        # Restore even on failure: a chdir that outlives the call is a trap for
        # whoever runs next, and in a test session that is another test.
        os.chdir(previous_cwd)

    counts = {
        t: con.execute(f"select count(*) from {t}").fetchone()[0]
        for t in ("dim_lifters", "dim_challenges", "bridge_memberships", "fct_lifts")
    }
    if quiet:
        con.close()
        return
    for table, n in counts.items():
        print(f"  {table:24} {n:4} rows")

    # Report what the reps filter dropped. A silent filter is how a total ends
    # up wrong in a way nobody can see, so the number is printed even when zero.
    raw_lifts = con.execute(
        "select count(*) from read_csv('data/lifts.csv', header = true, delim = ',', "
        "columns = {'lift_id': 'VARCHAR', 'lifter_id': 'VARCHAR', 'lift_date': 'DATE', "
        "'weight_kg': 'DOUBLE', 'reps': 'INTEGER'})"
    ).fetchone()[0]
    dropped = raw_lifts - counts["fct_lifts"]
    print(f"\n  {dropped} of {raw_lifts} logged sets excluded (reps outside 1-12, or weight <= 0)")

    # Orphans are visible, not silently absent. Every metric scopes to a
    # challenge, so these lifters contribute to nothing -- which is correct,
    # and worth saying out loud rather than discovering later.
    orphans = con.execute("""
        select count(*) from dim_lifters l
        where not exists (
            select 1 from bridge_memberships m where m.lifter_id = l.lifter_id
        )
    """).fetchone()[0]
    if orphans:
        print(f"  {orphans} lifter(s) belong to no challenge and are in no metric")

    con.close()
    print(f"\n  Wrote {db_path}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else DB_PATH)
