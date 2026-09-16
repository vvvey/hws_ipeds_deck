"""Build data/ipeds_deck.duckdb from the parquet extract (optional, local use).

The Streamlit app does this on its own at first launch; run this to pre-build
or rebuild the file by hand:

    python build_db.py            # build if missing or incomplete
    python build_db.py --force    # rebuild from scratch
"""
from __future__ import annotations

import sys

from core.data import build_database, IPEDS_DB_PATH


def main() -> None:
    force = "--force" in sys.argv[1:]
    path = build_database(force=force)
    import duckdb
    con = duckdb.connect(str(path), read_only=True)
    try:
        for (name,) in con.execute("SHOW TABLES").fetchall():
            n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            print(f"{name:6s} {n:>10,} rows")
    finally:
        con.close()
    print(f"built {path} ({IPEDS_DB_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
