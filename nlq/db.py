"""Read-only access to the warehouse.

Opened read-only on purpose: nothing in the query path may write. The only
writer is warehouse/build.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent


class Warehouse:
    def __init__(self, db_path: str | None = None):
        self.path = db_path or os.environ.get("DUCKDB_PATH", str(REPO / "warehouse.duckdb"))
        if not Path(self.path).exists():
            raise FileNotFoundError(
                f"No warehouse at {self.path}. Build it first:\n    python warehouse/build.py"
            )
        self.con = duckdb.connect(self.path, read_only=True)

    def run(self, sql: str, args: list | None = None) -> list[tuple]:
        return self.con.execute(sql, args or []).fetchall()

    def entity_values(self, table: str, key: str, label: str) -> list[tuple[str, str]]:
        """(key, label) pairs for an entity, e.g. every challenge or lifter."""
        return [(str(k), str(v)) for k, v in self.run(f"select {key}, {label} from {table} order by {label}")]

    def close(self) -> None:
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
